"""This is Gittip's payday algorithm.

Exchanges (moving money between Gittip and the outside world) and transfers
(moving money amongst Gittip users) happen within an isolated event called
payday. This event has duration (it's not punctiliar).

Payday is designed to be crash-resistant. Everything that can be rolled back
happens inside a single DB transaction. Exchanges cannot be rolled back, so they
immediately affect the participant's balance.

"""
from __future__ import unicode_literals

import itertools

from balanced import CardHold

import aspen.utils
from aspen import log
from gittip.billing.exchanges import (
    ach_credit, cancel_card_hold, capture_card_hold, create_card_hold, upcharge
)
from gittip.exceptions import (
    NegativeBalance, NoBalancedCustomerHref, NotWhitelisted
)
from gittip.models import check_db
from psycopg2 import IntegrityError


class NoPayday(Exception):
    __str__ = lambda self: "No payday found where one was expected."


class Payday(object):
    """Represent an abstract event during which money is moved.

    On Payday, we want to use a participant's Gittip balance to settle their
    tips due (pulling in more money via credit card as needed), but we only
    want to use their balance at the start of Payday. Balance changes should be
    atomic globally per-Payday.

    Here's the call structure of the Payday.run method:

        run
            payin
                prepare
                create_card_holds
                transfer_tips
                transfer_takes
                settle_card_holds
                update_balances
                take_over_balances
            payout
            update_stats
            update_receiving_amounts
            end

    """


    @classmethod
    def start(cls):
        """Try to start a new Payday.

        If there is a Payday that hasn't finished yet, then the UNIQUE
        constraint on ts_end will kick in and notify us of that. In that case
        we load the existing Payday and work on it some more. We use the start
        time of the current Payday to synchronize our work.

        """
        try:
            d = cls.db.one("""
                INSERT INTO paydays DEFAULT VALUES
                RETURNING id, (ts_start AT TIME ZONE 'UTC') AS ts_start, stage
            """, back_as=dict)
            log("Starting a new payday.")
        except IntegrityError:  # Collision, we have a Payday already.
            d = cls.db.one("""
                SELECT id, (ts_start AT TIME ZONE 'UTC') AS ts_start, stage
                  FROM paydays
                 WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
            """, back_as=dict)
            log("Picking up with an existing payday.")

        d['ts_start'] = d['ts_start'].replace(tzinfo=aspen.utils.utc)

        log("Payday started at %s." % d['ts_start'])

        payday = Payday()
        payday.__dict__.update(d)
        return payday


    def run(self):
        """This is the starting point for payday.

        This method runs every Thursday. It is structured such that it can be
        run again safely (with a newly-instantiated Payday object) if it
        crashes.

        """
        self.db.self_check()

        _start = aspen.utils.utcnow()
        log("Greetings, program! It's PAYDAY!!!!")

        if self.stage < 1:
            self.payin()
            self.mark_stage_done()
        if self.stage < 2:
            self.payout()
            self.mark_stage_done()
        if self.stage < 3:
            self.update_stats()
            self.update_receiving_amounts()
            self.mark_stage_done()

        self.end()

        _end = aspen.utils.utcnow()
        _delta = _end - _start
        fmt_past = "Script ran for {age} (%s)." % _delta
        log(aspen.utils.to_age(_start, fmt_past=fmt_past))


    def payin(self):
        """The first stage of payday where we charge credit cards and transfer
        money internally between participants.
        """
        with self.db.get_cursor() as cursor:
            self.prepare(cursor, self.ts_start)
            holds = self.create_card_holds(cursor)
            self.transfer_tips(cursor)
            self.transfer_takes(cursor, self.ts_start)
            self.settle_card_holds(cursor, holds)
            self.update_balances(cursor)
            check_db(cursor)
        self.take_over_balances()


    @staticmethod
    def prepare(cursor, ts_start):
        """Prepare the DB: we need temporary tables with indexes and triggers.
        """
        cursor.run("""

        -- Create the necessary temporary tables and indexes

        DROP TABLE IF EXISTS pay_participants CASCADE;
        CREATE TEMPORARY TABLE pay_participants AS
            SELECT id
                 , username
                 , claimed_time
                 , balance AS old_balance
                 , balance AS new_balance
                 , balanced_customer_href
                 , last_bill_result
                 , is_suspicious
                 , goal
              FROM participants
             WHERE is_suspicious IS NOT true
               AND claimed_time < %(ts_start)s
          ORDER BY claimed_time;

        CREATE UNIQUE INDEX ON pay_participants (id);
        CREATE UNIQUE INDEX ON pay_participants (username);

        DROP TABLE IF EXISTS pay_transfers CASCADE;
        CREATE TEMPORARY TABLE pay_transfers AS
            SELECT *
              FROM transfers t
             WHERE t.timestamp > %(ts_start)s;

        DROP TABLE IF EXISTS pay_tips CASCADE;
        CREATE TEMPORARY TABLE pay_tips AS
            SELECT tipper, tippee, amount
              FROM ( SELECT DISTINCT ON (tipper, tippee) *
                       FROM tips
                      WHERE mtime < %(ts_start)s
                   ORDER BY tipper, tippee, mtime DESC
                   ) t
              JOIN pay_participants p ON p.username = t.tipper
              JOIN pay_participants p2 ON p2.username = t.tippee
             WHERE t.amount > 0
               AND (p2.goal IS NULL or p2.goal >= 0)
               AND ( SELECT id
                       FROM pay_transfers t2
                      WHERE t.tipper = t2.tipper
                        AND t.tippee = t2.tippee
                        AND context = 'tip'
                   ) IS NULL
          ORDER BY p.claimed_time ASC, t.ctime ASC;

        CREATE INDEX ON pay_tips (tipper);
        CREATE INDEX ON pay_tips (tippee);
        ALTER TABLE pay_tips ADD COLUMN is_funded boolean;

        ALTER TABLE pay_participants ADD COLUMN giving_today numeric(35,2);
        UPDATE pay_participants
           SET giving_today = COALESCE((
                   SELECT sum(amount)
                     FROM pay_tips
                    WHERE tipper = username
               ), 0);

        DROP TABLE IF EXISTS pay_takes;
        CREATE TEMPORARY TABLE pay_takes
        ( team text
        , member text
        , amount numeric(35,2)
        );


        -- Prepare a statement that makes and records a transfer

        CREATE OR REPLACE FUNCTION transfer(text, text, numeric, context_type)
        RETURNS void AS $$
            BEGIN
                UPDATE pay_participants
                   SET new_balance = (new_balance - $3)
                 WHERE username = $1;
                UPDATE pay_participants
                   SET new_balance = (new_balance + $3)
                 WHERE username = $2;
                INSERT INTO transfers
                            (tipper, tippee, amount, context)
                     VALUES ( ( SELECT p.username
                                  FROM participants p
                                  JOIN pay_participants p2 ON p.id = p2.id
                                 WHERE p2.username = $1 )
                            , ( SELECT p.username
                                  FROM participants p
                                  JOIN pay_participants p2 ON p.id = p2.id
                                 WHERE p2.username = $2 )
                            , $3
                            , $4
                            );
            END;
        $$ LANGUAGE plpgsql;


        -- Create a trigger to process tips

        CREATE OR REPLACE FUNCTION process_tip() RETURNS trigger AS $$
            BEGIN
                EXECUTE transfer(NEW.tipper, NEW.tippee, NEW.amount, 'tip');
                RETURN NULL;
            END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER process_tip AFTER UPDATE OF is_funded ON pay_tips
            FOR EACH ROW
            WHEN (NEW.is_funded IS true AND OLD.is_funded IS NOT true)
            EXECUTE PROCEDURE process_tip();


        -- Create a trigger to process takes

        CREATE OR REPLACE FUNCTION process_take() RETURNS trigger AS $$
            DECLARE
                actual_amount numeric(35,2);
                team_balance numeric(35,2);
            BEGIN
                team_balance := (
                    SELECT new_balance
                      FROM pay_participants
                     WHERE username = NEW.team
                );
                actual_amount := NEW.amount;
                IF (team_balance < NEW.amount) THEN
                    actual_amount := team_balance;
                END IF;
                EXECUTE transfer(NEW.team, NEW.member, actual_amount, 'take');
                RETURN NULL;
            END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER process_take AFTER INSERT ON pay_takes
            FOR EACH ROW EXECUTE PROCEDURE process_take();


        -- Save the stats we already have

        UPDATE paydays
           SET nparticipants = (SELECT count(*) FROM pay_participants)
             , ncc_missing = (
                   SELECT count(*)
                     FROM pay_participants
                    WHERE old_balance < giving_today
                      AND ( balanced_customer_href IS NULL
                            OR
                            last_bill_result IS NULL
                          )
               )

        """, dict(ts_start=ts_start))
        log('Prepared the DB.')


    @staticmethod
    def fetch_card_holds(participant_ids):
        holds = {}
        for hold in CardHold.query.filter(CardHold.f.meta.state == 'new'):
            state = 'new'
            if hold.failure_reason:
                state = 'failed'
            elif hold.voided_at:
                state = 'cancelled'
            elif getattr(hold, 'debit_href', None):
                state = 'captured'
            if state != 'new':
                hold.meta['state'] = state
                hold.save()
                continue
            p_id = int(hold.meta['participant_id'])
            if p_id in participant_ids:
                holds[p_id] = hold
            else:
                cancel_card_hold(hold)
        return holds


    def create_card_holds(self, cursor):

        # Get the list of participants to create card holds for
        participants = cursor.all("""
            SELECT *
              FROM pay_participants
             WHERE old_balance < giving_today
               AND balanced_customer_href IS NOT NULL
               AND last_bill_result IS NOT NULL
               AND is_suspicious IS false
        """)
        if not participants:
            return {}

        # Fetch existing holds
        participant_ids = set(p.id for p in participants)
        holds = self.fetch_card_holds(participant_ids)

        # Create new holds and check amounts of existing ones
        for p in participants:
            amount = p.giving_today
            if p.old_balance < 0:
                amount -= p.old_balance
            if p.id in holds:
                charge_amount = upcharge(amount)[0]
                if holds[p.id].amount >= charge_amount * 100:
                    continue
                else:
                    # The amount is too low, cancel the hold and make a new one
                    cancel_card_hold(holds.pop(p.id))
            hold, error = create_card_hold(self.db, p, amount)
            if error:
                self.mark_charge_failed(cursor)
            else:
                holds[p.id] = hold

        # Update the values of last_bill_result in our temporary table
        cursor.run("""
            UPDATE pay_participants p
               SET last_bill_result = p2.last_bill_result
              FROM participants p2
             WHERE p.id = p2.id
        """)

        return holds


    @staticmethod
    def transfer_tips(cursor):
        cursor.run("""

        UPDATE pay_tips t
           SET is_funded = true
          FROM pay_participants p
         WHERE p.username = t.tipper
           AND p.last_bill_result = '';

        UPDATE pay_tips t
           SET is_funded = true
         WHERE is_funded IS NOT true
           AND amount <= (
                   SELECT new_balance
                     FROM pay_participants p
                    WHERE p.username = t.tipper
               );

        """)


    @staticmethod
    def transfer_takes(cursor, ts_start):
        cursor.run("""

        INSERT INTO pay_takes
            SELECT team, member, amount
              FROM ( SELECT DISTINCT ON (team, member)
                            team, member, amount, ctime
                       FROM takes
                      WHERE mtime < %(ts_start)s
                   ORDER BY team, member, mtime DESC
                   ) t
             WHERE t.amount > 0
               AND t.team IN (SELECT username FROM pay_participants)
               AND t.member IN (SELECT username FROM pay_participants)
               AND ( SELECT id
                       FROM pay_transfers t2
                      WHERE t.team = t2.tipper
                        AND t.member = t2.tippee
                        AND context = 'take'
                   ) IS NULL
          ORDER BY t.team, t.ctime DESC;

        """, dict(ts_start=ts_start))


    def settle_card_holds(self, cursor, holds):
        participants = cursor.all("""
            SELECT *
              FROM pay_participants
             WHERE new_balance < 0
        """)

        # Capture holds to bring balances back up to (at least) zero
        i = 0
        for p in participants:
            assert p.id in holds
            amount = -p.new_balance
            capture_card_hold(self.db, p, amount, holds.pop(p.id))
            i += 1
        log("Captured %i card holds." % i)

        # Cancel the remaining holds
        for hold in holds.values():
            cancel_card_hold(hold)
        log("Canceled %i card holds." % len(holds))


    @staticmethod
    def update_balances(cursor):
        participants = cursor.all("""

            UPDATE participants p
               SET balance = (balance + p2.new_balance - p2.old_balance)
              FROM pay_participants p2
             WHERE p.id = p2.id
               AND p2.new_balance <> p2.old_balance
         RETURNING p.id
                 , p.username
                 , balance AS new_balance
                 , ( SELECT balance
                       FROM participants p3
                      WHERE p3.id = p.id
                   ) AS cur_balance;

        """)
        # Check that balances aren't becoming (more) negative
        for p in participants:
            if p.new_balance < 0 and p.new_balance < p.cur_balance:
                raise NegativeBalance(p)
        log("Updated the balances of %i participants." % len(participants))


    def take_over_balances(self):
        """If an account that receives money is taken over during payin we need
        to transfer the balance to the absorbing account.
        """
        for i in itertools.count():
            if i > 10:
                raise Exception('possible infinite loop')
            count = self.db.one("""

                DROP TABLE IF EXISTS temp;
                CREATE TEMPORARY TABLE temp AS
                    SELECT archived_as, absorbed_by, balance AS archived_balance
                      FROM absorptions a
                      JOIN participants p ON a.archived_as = p.username
                     WHERE balance > 0;

                SELECT count(*) FROM temp;

            """)
            if not count:
                break
            self.db.run("""

                INSERT INTO transfers (tipper, tippee, amount, context)
                    SELECT archived_as, absorbed_by, archived_balance, 'take-over'
                      FROM temp;

                UPDATE participants
                   SET balance = (balance - archived_balance)
                  FROM temp
                 WHERE username = archived_as;

                UPDATE participants
                   SET balance = (balance + archived_balance)
                  FROM temp
                 WHERE username = absorbed_by;

            """)


    def payout(self):
        """This is the second stage of payday in which we send money out to the
        bank accounts of participants.
        """
        i = 0
        log("Starting payout loop.")
        participants = self.db.all("""
            SELECT p.*::participants FROM participants p WHERE balance > 0
        """)
        for i, participant in enumerate(participants, start=1):
            withhold = participant.giving + participant.pledging
            try:
                error = ach_credit(self.db, participant, withhold)
                if error:
                    self.mark_ach_failed()
            except NoBalancedCustomerHref:
                continue
            except NotWhitelisted:
                if participant.is_suspicious is None:
                    log("UNREVIEWED: %s" % participant.username)
        log("Did payout for %d participants." % i)
        self.db.self_check()
        log("Checked the DB.")


    def update_stats(self):
        self.db.run("""\

            WITH our_transfers AS (
                     SELECT *
                       FROM transfers
                      WHERE "timestamp" >= %(ts_start)s
                 )
               , our_tips AS (
                     SELECT *
                       FROM our_transfers
                      WHERE context = 'tip'
                 )
               , our_pachinkos AS (
                     SELECT *
                       FROM our_transfers
                      WHERE context = 'take'
                 )
               , our_exchanges AS (
                     SELECT *
                       FROM exchanges
                      WHERE "timestamp" >= %(ts_start)s
                 )
               , our_achs AS (
                     SELECT *
                       FROM our_exchanges
                      WHERE amount < 0
                 )
               , our_charges AS (
                     SELECT *
                       FROM our_exchanges
                      WHERE amount > 0
                 )
            UPDATE paydays
               SET nactive = (
                       SELECT DISTINCT count(*) FROM (
                           SELECT tipper FROM our_transfers
                               UNION
                           SELECT tippee FROM our_transfers
                       ) AS foo
                   )
                 , ntippers = (SELECT count(DISTINCT tipper) FROM our_transfers)
                 , ntips = (SELECT count(*) FROM our_tips)
                 , npachinko = (SELECT count(*) FROM our_pachinkos)
                 , pachinko_volume = (SELECT sum(amount) FROM our_pachinkos)
                 , ntransfers = (SELECT count(*) FROM our_transfers)
                 , transfer_volume = (SELECT sum(amount) FROM our_transfers)
                 , nachs = (SELECT count(*) FROM our_achs)
                 , ach_volume = (SELECT COALESCE(sum(amount), 0) FROM our_achs)
                 , ach_fees_volume = (SELECT sum(fee) FROM our_achs)
                 , ncharges = (SELECT count(*) FROM our_charges)
                 , charge_volume = (
                       SELECT COALESCE(sum(amount + fee), 0)
                         FROM our_charges
                   )
                 , charge_fees_volume = (SELECT sum(fee) FROM our_charges)
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz

        """, {'ts_start': self.ts_start})
        log("Updated payday stats.")


    def update_receiving_amounts(self):
        UPDATE = """
            CREATE OR REPLACE TEMPORARY VIEW total_receiving AS
                SELECT tippee, sum(amount) AS amount, count(*) AS ntippers
                  FROM current_tips
                  JOIN participants p ON p.username = tipper
                 WHERE p.is_suspicious IS NOT TRUE
                   AND p.last_bill_result = ''
                   AND amount > 0
              GROUP BY tippee;

            UPDATE participants
               SET receiving = (amount + taking)
                 , npatrons = ntippers
              FROM total_receiving
             WHERE tippee = username;
        """
        with self.db.get_cursor() as cursor:
            cursor.execute(UPDATE)
        log("Updated receiving amounts.")


    def end(self):
        self.ts_end = self.db.one("""\

            UPDATE paydays
               SET ts_end=now()
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING ts_end AT TIME ZONE 'UTC'

        """, default=NoPayday).replace(tzinfo=aspen.utils.utc)


    # Record-keeping.
    # ===============

    @staticmethod
    def mark_charge_failed(cursor):
        cursor.one("""\

            UPDATE paydays
               SET ncc_failing = ncc_failing + 1
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, default=NoPayday)


    def mark_ach_failed(self):
        self.db.one("""\

            UPDATE paydays
               SET nach_failing = nach_failing + 1
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, default=NoPayday)


    def mark_stage_done(self):
        self.db.one("""\

            UPDATE paydays
               SET stage = stage + 1
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, default=NoPayday)
