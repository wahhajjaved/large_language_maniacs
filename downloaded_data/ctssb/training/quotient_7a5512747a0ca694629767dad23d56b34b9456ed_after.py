
import os

from twisted.trial import unittest
from twisted.python import filepath

from epsilon import extime

from axiom import store

from xquotient import mimepart
from xquotient.mimestorage import Part
from xquotient.test import test_grabber
from xquotient.test.util import MIMEReceiverMixin, PartMaker

from xmantissa import ixmantissa

def msg(s):
    return '\r\n'.join(s.splitlines())

class MessageTestMixin:
    trivialMessage = msg("""\
From: alice@example.com
To: bob@example.com
Subject: a test message, comma separated
Date: Tue, 11 Oct 2005 14:25:12 GMT
Junk\xa0Header: value
References: <one@domain>\t<two@domain>\x20
\t<three@domain>

Hello Bob,
  How are you?
-A
""")

    def assertHeadersEqual(self, a, b):
        self.assertEquals(a.name, b.name)
        self.assertEquals(a.value, b.value)

    def assertTrivialMessageStructure(self, msg):
        map(self.assertHeadersEqual,
            list(msg.getAllHeaders())[:-1],
            [mimepart.Header(u"from", "alice@example.com"),
             mimepart.Header(u"to", "bob@example.com"),
             mimepart.Header(u"subject", "a test message, comma separated"),
             mimepart.Header(u"date", "Tue, 11 Oct 2005 14:25:12 GMT"),
             mimepart.Header(u"junkheader", "value"),
             mimepart.Header(u"references", "<one@domain>"),
             mimepart.Header(u"references", "<two@domain>"),
             mimepart.Header(u"references", "<three@domain>")])

        self.assertEquals(msg.getHeader(u"from"), "alice@example.com")
        self.assertEquals(msg.getHeader(u"to"), "bob@example.com")
        self.assertEquals(msg.getHeader(u"subject"), "a test message, comma separated")
        self.assertEquals(msg.getHeader(u"date"), 'Tue, 11 Oct 2005 14:25:12 GMT')
        self.assertEquals(msg.getHeader(u"junkheader"), "value")
        self.assertEquals([hdr.value for hdr in msg.getHeaders(u"references")],
                          [u"<one@domain>", u"<two@domain>", u"<three@domain>"])

    def testTrivialMessage(self):
        self._messageTest(self.trivialMessage, self.assertTrivialMessageStructure)



    messageWithUnicode = msg("""\
From: =?utf-8?b?VMOpc3Qgx5NzZXIgPHRlc3R1c2VyQGV4YW1wbGUuY29tPg==?=

Body.
""")


    def assertUnicodeHeaderValues(self, msg):
        self.assertEquals(
            msg.getHeader(u"from"),
            u"T\N{LATIN SMALL LETTER E WITH ACUTE}st "
            u"\N{LATIN CAPITAL LETTER U WITH CARON}ser "
            u"<testuser@example.com>")


    def testUnicodeHeaderValues(self):
        """
        MIME Headers may be encoded in various ways.  Assert that none of these
        encoding details make it into the resulting Header objects and that the
        non-ASCII payload is correctly interpreted.
        """
        self._messageTest(self.messageWithUnicode, self.assertUnicodeHeaderValues)


    multipartMessage = msg("""\
Envelope-to: test@domain.tld
Received: from pool-138-88-80-171.res.east.verizon.net
	([138.88.80.171] helo=meson.dyndns.org ident=69gnV1Y3MozcsVOT)
	by pyramid.twistedmatrix.com with esmtp (Exim 3.35 #1 (Debian))
	id 181WHR-0002Rq-00
	for <test@domain.tld>; Tue, 15 Oct 2002 13:18:57 -0500
Received: by meson.dyndns.org (Postfix, from userid 1000)
	id 34DEB13E95; Tue, 15 Oct 2002 14:20:18 -0400 (EDT)
Date: Tue, 15 Oct 2002 14:20:18 -0400
From: Jp Calderone <exarkun@blargchoo.choo.choo.dyndns.org>
To: test@domain.tld
Subject: [user@address: My Cool Apartment!]
Message-ID: <20021015182018.GA11673@unique.oh.yea>
Mime-Version: 1.0
Content-Type: multipart/signed; micalg=x-unknown;
	protocol="application/pgp-signature"; boundary="24zk1gE8NUlDmwG9"
Content-Disposition: inline
User-Agent: Mutt/1.3.25i
Content-Length: 2003
Lines: 72
Status: RO
x-pop3-uid: 3dbf299600000017 twistedmatrix.com


--24zk1gE8NUlDmwG9
Content-Type: multipart/mixed; boundary="h31gzZEtNLTqOjlF"
Content-Disposition: inline


--h31gzZEtNLTqOjlF
Content-Type: text/plain; charset=us-ascii
Content-Disposition: inline
Content-Transfer-Encoding: quoted-printable


--=20
   Know what I pray for? The strength to change what I can, the inability to
accept what I can't and the incapacity to tell the difference.    -- Calvin
--
 2:00pm up 147 days, 14:57, 4 users, load average: 0.00, 0.02, 0.00

--h31gzZEtNLTqOjlF
Content-Type: message/rfc822
Content-Disposition: inline

Return-Path: <dynamox@springstreet.com>
Delivered-To: thisuser@guy.wherever
Received: from mx1.springstreet.com (unknown [206.131.172.28])
	by meson.dyndns.org (Postfix) with ESMTP id E027314187
	for <exarkun@choo.choo.choo.dyndns.org>; Wed, 18 Sep 2002 00:27:14 -0400 (EDT)
Received: from app2.springstreet.com (app2.admin.springstreet.com
	[10.0.149.2])
	by mx1.springstreet.com (8.11.6/8.11.6) with ESMTP id g8I4RUe47820
	for <exarkun@xxxx.org>; Tue, 17 Sep 2002 21:27:30 -0700 (PDT)
	(envelope-from dynamox@springstreet.com)
Received: (from dynamox@localhost)
	by app2.springstreet.com (8.10.2+Sun/8.10.2) id g8I4RUb22565;
	Tue, 17 Sep 2002 21:27:30 -0700 (PDT)
Date: Tue, 17 Sep 2002 21:27:30 -0700 (PDT)
Message-Id: <200209180427.g8I4RUb22565@app2.springstreet.com>
To: this.field.is.for@the.user.it.is.for
From: someuser@anotherdomain.com
SUBJECT: My Cool Apartment!

jp,

Hey! Check out this great apartment I found at Homestore.com apartments &
rentals! You can visit it here:
http://www.springstreet.com/propid/246774?source=1xxctb079


cathedral ceilings



<message id:1032323249933719>

--h31gzZEtNLTqOjlF--

--24zk1gE8NUlDmwG9
Content-Type: application/pgp-signature
Content-Disposition: inline

-----BEGIN PGP SIGNED MESSAGE-----
Hash: SHA1


-----BEGIN PGP SIGNATURE-----
Version: GnuPG v1.0.7 (GNU/Linux)

iD8DBQE9rFxhedcO2BJA+4YRAjZqAKC6jZcmEZu0tInRreBjTbFcIh7rfACdEDhZ
oTZw+Ovl1BvLcE+pK9VFxxY=
=Uds2
-----END PGP SIGNATURE-----

--24zk1gE8NUlDmwG9--
""")

    def assertMultipartMessageStructure(self, msg):
        pass

    def testMultipartMessage(self):
        self._messageTest(self.multipartMessage, self.assertMultipartMessageStructure)


class ParsingTestCase(unittest.TestCase, MessageTestMixin):
    def _messageTest(self, source, assertMethod):
        deliveryDir = self.mktemp()
        os.makedirs(deliveryDir)
        f = store.AtomicFile(
            filepath.FilePath(deliveryDir).child('tmp.eml').path,
            filepath.FilePath(deliveryDir).child('message.eml'))
        mr = mimepart.MIMEMessageReceiver(f)
        msg = mr.feedStringNow(source)
        assertMethod(msg)



class PersistenceTestCase(unittest.TestCase, MessageTestMixin, MIMEReceiverMixin):
    def _messageTest(self, source, assertMethod):
        mr = self.setUpMailStuff()
        msg = mr.feedStringNow(source)
        assertMethod(msg)


    def assertIndexability(self, msg):
        fi = ixmantissa.IFulltextIndexable(msg.message)
        self.assertEquals(fi.uniqueIdentifier(), unicode(msg.message.storeID))
        self.assertEquals(sorted(fi.textParts()), [
            u'Hello Bob,\n  How are you?\n-A\n',
            u'a test message, comma separated',
            u'alice@example.com alice example com alice@example.com'])
        self.assertEquals(fi.keywordParts(), {
            u'subject': u'a test message, comma separated',
            u'sender': u'alice@example.com alice example com alice@example.com'})
        self.assertEquals(fi.documentType(), msg.message.typeName)


    def testIndexability(self):
        """
        Test that the result is adaptable to IFulltextIndexable and the
        resulting object spits out the right data.
        """
        self._messageTest(self.trivialMessage, self.assertIndexability)


    def testAttachmentsAllHaveLength(self):
        def checkAttachments(msgitem):
            for att in msgitem.walkAttachments():
                self.assertNotEquals(att.part.bodyLength, None)
        self._messageTest(messageWithEmbeddedMessage, checkAttachments)
        self._messageTest(truncatedMultipartMessage, checkAttachments)

    def testPartIDs(self):
        mr = self.setUpMailStuff()
        part = mr.feedStringNow(self.multipartMessage)
        self.assertEquals(part.partID, 0)
        partIDs = list(part.store.query(
                            Part, sort=Part.partID.ascending).getColumn('partID'))
        self.assertEquals(partIDs, range(len(partIDs)))

    alternativeInsideMixed = PartMaker('multipart/mixed', 'mixed',
                                PartMaker('multipart/alternative', 'alt',
                                    PartMaker('text/plain', 'plain-1'),
                                    PartMaker('text/html', 'html-1')),
                                PartMaker('text/plain', 'plain-2')).make()

    def testAlternativeInsideMixed(self):
        part = self.setUpMailStuff().feedStringNow(self.alternativeInsideMixed)

        self.assertEquals(part.getContentType(), 'multipart/mixed')

        def getKidsAndCheckTypes(parent, types):
            kids = list(part.store.query(Part, Part.parent == parent))
            self.assertEquals(list(p.getContentType() for p in kids), types)
            return kids

        kids = getKidsAndCheckTypes(part, ['multipart/alternative', 'text/plain'])

        # RFC 2046, section 5.1.1, says:
        #    "The CRLF preceding the boundary delimiter line is conceptually attached
        #     to the boundary so that it is possible to have a part that does not end
        #     with a CRLF (line break). Body parts that must be considered to end with
        #     line breaks, therefore, must have two CRLFs preceding the boundary
        #     delimiter line, the first of which is part of the preceding body part,
        #     and the second of which is part of the encapsulation boundary."
        #
        # - there is only one CRLF between the end of the body of each part
        # and the next boundary, which would seem to indicate that we shouldn't
        # have to to embed newlines to get these assertions to pass

        self.assertEquals(kids[-1].getBody(), 'plain-2\n')

        gkids = getKidsAndCheckTypes(kids[0], ['text/plain', 'text/html'])

        self.assertEquals(gkids[0].getBody(), 'plain-1\n')
        self.assertEquals(gkids[1].getBody(), 'html-1\n')

        def checkDisplayBodies(parent, ctype, bodies):
            displayParts = list(parent.walkMessage(ctype))
            self.assertEquals(list(p.part.getBody() for p in displayParts), bodies)

        # we're calling walkMessage() on the multipart/mixed part,
        # so we should get back 'plain-1' and 'plain-2', not 'html-1',
        # because it's inside a nested multipart/alternative with 'plain-1'

        checkDisplayBodies(part, 'text/plain', ['plain-1\n', 'plain-2\n'])

        # this should still show us 'plain-2', but 'html-1' should get
        # selected from the multipart/alternative part

        checkDisplayBodies(part, 'text/html', ['html-1\n', 'plain-2\n'])

        # now try the same on the multipart/alternative part directly.
        # the results should be the same, except plain-2 shouldn't be
        # considered, because it's a sibling part

        checkDisplayBodies(kids[0], 'text/plain', ['plain-1\n'])
        checkDisplayBodies(kids[0], 'text/html',  ['html-1\n'])

    typelessMessage = msg("""\
To: you
From: nobody

haha
""")

    def testContentTypeNotNone(self):
        self._messageTest(self.typelessMessage,
                          lambda part: self.assertEquals(part.getContentType(),
                                                         'text/plain'))

    datelessMessage = msg("""\
Received: Wed, 15 Feb 2006 03:58:50 GMT

Some body
""")

    def testSentWhen(self):
        def assertSentWhen(part):
            self.assertEquals(
                part.message.sentWhen,
                extime.Time.fromRFC2822("Wed, 15 Feb 2006 03:58:50 GMT"))

        self._messageTest(self.datelessMessage, assertSentWhen)

messageWithEmbeddedMessage = """\
Return-path: <bounce-debian-bugs-dist=exarkun=divmod.org@lists.debian.org>
Envelope-to: exarkun@divmod.org
Received: from exprod6mx95.postini.com ([12.158.36.79] helo=psmtp.com)
	by tesla.divmod.net with smtp (Exim 3.35 #1 (Debian))
	id 1ArcnU-0001Rj-00
	for <exarkun@divmod.org>; Fri, 13 Feb 2004 07:51:57 -0500
Received: from source ([146.82.138.6]) by exprod6mx95.postini.com ([12.158.35.251]) with SMTP;
	Fri, 13 Feb 2004 06:51:55 CST
Received: from localhost (localhost [127.0.0.1])
	by murphy.debian.org (Postfix) with QMQP
	id 1C0E8EAE4; Fri, 13 Feb 2004 06:51:55 -0600 (CST)
Old-Return-Path: <debbugs@bugs.debian.org>
X-Original-To: debian-bugs-dist@lists.debian.org
Received: from spohr.debian.org (spohr.debian.org [128.193.0.4])
	by murphy.debian.org (Postfix) with ESMTP id F2312EABE
	for <debian-bugs-dist@lists.debian.org>; Fri, 13 Feb 2004 06:51:53 -0600 (CST)
Received: from debbugs by spohr.debian.org with local (Exim 3.35 1 (Debian))
	id 1Arcjj-0002bB-00; Fri, 13 Feb 2004 04:48:03 -0800
X-Loop: owner@bugs.debian.org
Subject: Bug#232531: libcommons-collections-java: Commons Collections 3.0 released
Reply-To: Arnaud Vandyck <avdyk@debian.org>, 232531@bugs.debian.org
Resent-From: Arnaud Vandyck <avdyk@debian.org>
Original-Sender: Arnaud Vandyck <arnaud.vandyck@ulg.ac.be>
Resent-To: debian-bugs-dist@lists.debian.org
Resent-Cc: Takashi Okamoto <tora@debian.org>
Resent-Date: Fri, 13 Feb 2004 12:48:03 UTC
Resent-Message-ID: <handler.232531.B.10766762649163@bugs.debian.org>
X-Debian-PR-Message: report 232531
X-Debian-PR-Package: libcommons-collections-java
X-Debian-PR-Keywords: 
Received: via spool by submit@bugs.debian.org id=B.10766762649163
          (code B ref -1); Fri, 13 Feb 2004 12:48:03 UTC
Received: (at submit) by bugs.debian.org; 13 Feb 2004 12:44:24 +0000
Received: from serv09.segi.ulg.ac.be [139.165.32.78] 
	by spohr.debian.org with esmtp (Exim 3.35 1 (Debian))
	id 1ArcgC-0002NM-00; Fri, 13 Feb 2004 04:44:24 -0800
Received: (qmail 16389 invoked by uid 504); 13 Feb 2004 13:43:52 +0100
Received: from arnaud.vandyck@ulg.ac.be by serv09.segi.ulg.ac.be by uid 501 with qmail-scanner-1.16 
 (clamscan: 0.60. spamassassin: 2.55.  Clear:. 
 Processed in 0.833584 secs); 13 Feb 2004 12:43:52 -0000
Received: from unknown (HELO oz.fapse.ulg.ac.be) ([139.165.77.198])
          (envelope-sender <arnaud.vandyck@ulg.ac.be>)
          by serv09.segi.ulg.ac.be (qmail-ldap-1.03) with SMTP
          for <submit@bugs.debian.org>; 13 Feb 2004 13:43:51 +0100
Received: from arnaud by oz.fapse.ulg.ac.be with local (Exim 4.30)
	id 1Arcfc-0005q9-Om
	for submit@bugs.debian.org; Fri, 13 Feb 2004 13:43:48 +0100
To: Debian Bug Tracking System <submit@bugs.debian.org>
From: Arnaud Vandyck <avdyk@debian.org>
X-Face: yuSM.z0$PasG_!+)P;ugu5P+@#JEocHIpArGcQZ^hcGos8:DBJ-tfTQYWyf`$2r0vfaoo7F| h.;Agl'@x8v]?{#ZLQDqSB:L^6RXGfF_fD+G9$c:)p<yycF[Da]*=*
Date: Fri, 13 Feb 2004 13:43:48 +0100
Message-ID: <87u11vxi7v.fsf@oz.fapse.ulg.ac.be>
User-Agent: Gnus/5.1006 (Gnus v5.10.6) Emacs/21.3 (gnu/linux)
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="=-=-="
Sender: Arnaud Vandyck <arnaud.vandyck@ulg.ac.be>
Delivered-To: submit@bugs.debian.org
X-Spam-Checker-Version: SpamAssassin 2.60-bugs.debian.org_2004_02_12 
	(1.212-2003-09-23-exp) on spohr.debian.org
X-Spam-Status: No, hits=-5.0 required=4.0 tests=HAS_PACKAGE autolearn=no 
	version=2.60-bugs.debian.org_2004_02_12
X-Spam-Level: 
X-Mailing-List: <debian-bugs-dist@lists.debian.org> 
X-Loop: debian-bugs-dist@lists.debian.org
List-Id: <debian-bugs-dist.lists.debian.org>
List-Post: <mailto:debian-bugs-dist@lists.debian.org>
List-Help: <mailto:debian-bugs-dist-request@lists.debian.org?subject=help>
List-Subscribe: <mailto:debian-bugs-dist-request@lists.debian.org?subject=subscribe>
List-Unsubscribe: <mailto:debian-bugs-dist-request@lists.debian.org?subject=unsubscribe>
Precedence: list
Resent-Sender: debian-bugs-dist-request@lists.debian.org
X-pstn-levels:     (S:99.9000 R:95.9108 P:95.9108 M:99.9590 C:78.1961 )
X-pstn-settings: 3 (1.0000:2.0000) r p m C 
X-pstn-addresses: from <avdyk@debian.org> [db-null] 
Status: RO

--=-=-=

Package: libcommons-collections-java
Version: 2.1-1
Severity: wishlist

Hi Takashi,

I do attach the announcement of the 3.0 release of colloections.

Cheers,


--=-=-=
Content-Type: message/rfc822
Content-Disposition: inline

X-From-Line: scolebourne@apache.org  Mon Jan 26 00:54:40 2004
Return-Path: <announcements-return-278-arnaud.vandyck=ulg.ac.be@jakarta.apache.org>
Delivered-To: arnaud.vandyck@ulg.ac.be
Received: (qmail 3201 invoked from network); 26 Jan 2004 02:59:13 +0100
Received: from unknown ([139.165.32.84])
          by serv19.segi.ulg.ac.be (qmail-ldap-1.03) with QMQP; 26 Jan 2004
 02:59:13 +0100
Delivered-To: CLUSTERHOST serv27.segi.ulg.ac.be arnaud.vandyck@ulg.ac.be
Received: (qmail 10028 invoked by uid 504); 26 Jan 2004 02:59:12 +0100
Received: from announcements-return-278-arnaud.vandyck=ulg.ac.be@jakarta.apache.org
 by serv27.segi.ulg.ac.be by uid 501 with qmail-scanner-1.16 
 (clamscan: 0.60. spamassassin: 2.55.  Clear:SA:0(-2.9/5.0):. 
 Processed in 11.147137 secs); 26 Jan 2004 01:59:12 -0000
Received: from unknown (HELO mail.apache.org) ([208.185.179.12])
          (envelope-sender
 <announcements-return-278-arnaud.vandyck=ulg.ac.be@jakarta.apache.org>)
          by serv27.segi.ulg.ac.be (qmail-ldap-1.03) with SMTP
          for <arnaud.vandyck@ulg.ac.be>; 26 Jan 2004 02:59:01 +0100
Received: (qmail 51838 invoked by uid 500); 26 Jan 2004 01:57:39 -0000
Mailing-List: contact announcements-help@jakarta.apache.org; run by ezmlm
Precedence: bulk
List-Unsubscribe: <mailto:announcements-unsubscribe@jakarta.apache.org>
List-Subscribe: <mailto:announcements-subscribe@jakarta.apache.org>
List-Help: <mailto:announcements-help@jakarta.apache.org>
List-Post: <mailto:announcements@jakarta.apache.org>
List-Id: "Jakarta Announcements List" <announcements.jakarta.apache.org>
Reply-To: "Jakarta General List" <general@jakarta.apache.org>
Delivered-To: mailing list announcements@jakarta.apache.org
Received: (qmail 5369 invoked from network); 26 Jan 2004 00:54:01 -0000
Message-ID: <004201c3e3a6$fc7c80c0$18638051@oemcomputer>
From: "Stephen Colebourne" <scolebourne@apache.org>
To: <announcements@jakarta.apache.org>
Date: Mon, 26 Jan 2004 00:54:40 -0000
X-Priority: 3
X-MSMail-Priority: Normal
X-Mailer: Microsoft Outlook Express 5.50.4133.2400
X-MimeOLE: Produced By Microsoft MimeOLE V5.50.4133.2400
X-SA-Exim-Mail-From: scolebourne@apache.org
Subject: [ANOUNCEMENT] Commons Collections 3.0 released
X-SA-Exim-Version: 3.1 (built Thu Oct 23 13:26:47 PDT 2003)
X-SA-Exim-Scanned: Yes
X-uvscan-result: clean (1Akv3z-0005sQ-8W)
X-Spam-Rating: daedalus.apache.org 1.6.2 0/1000/N
X-Spam-Status: No, hits=-2.9 required=5.0
	tests=BAYES_20,KNOWN_MAILING_LIST
	version=2.55
X-Spam-Level: 
X-Spam-Checker-Version: SpamAssassin 2.55 (1.174.2.19-2003-05-19-exp)
X-Content-Length: 755
Xref: oz.fapse.ulg.ac.be alioth.pkg-java-maintainers:221
Lines: 22
MIME-Version: 1.0

The Commons Collections team is pleased to announce that the Commons
Collections 3.0 release is now available.

Commons Collections is a library providing implementations, interfaces and
utilities enhancing the Java Collections Framework.

This is a major release. If you are upgrading, please read the release notes
for more information.

Links:
Website: http://jakarta.apache.org/commons/collections/index.html
Binary downloads: http://jakarta.apache.org/site/binindex.cgi
Source downloads: http://jakarta.apache.org/site/sourceindex.cgi



---------------------------------------------------------------------
To unsubscribe, e-mail: announcements-unsubscribe@jakarta.apache.org
For additional commands, e-mail: announcements-help@jakarta.apache.org




--=-=-=



-- 
  .''`. 
 : :' :rnaud
 `. `'  
   `-    

--=-=-=--


-- 
To UNSUBSCRIBE, email to debian-bugs-dist-request@lists.debian.org
with a subject of "unsubscribe". Trouble? Contact listmaster@lists.debian.org

"""

truncatedMultipartMessage = """
Envelope-to: exarkun@twistedmatrix.com
Received: from fuchsia.puzzling.org ([64.91.227.43])
        by pyramid.twistedmatrix.com with esmtp (Exim 3.35 #1 (Debian))
        id 1BEmL5-0007rB-00; Sat, 17 Apr 2004 03:42:19 -0600
Received: from localhost (localhost [127.0.0.1])
        by fuchsia.puzzling.org (Postfix) with ESMTP
        id 26C44944B0; Sat, 17 Apr 2004 19:43:37 +1000 (EST)
Received: from fuchsia.puzzling.org ([127.0.0.1])
        by localhost (puzzling.org [127.0.0.1]) (amavisd-new, port 10024)
        with ESMTP id 13403-06; Sat, 17 Apr 2004 19:43:36 +1000 (EST)
Received: from c-24-130-52-47.we.client2.attbi.com (c-24-130-52-47.we.client2.attbi.com [24.130.52.47])
        by fuchsia.puzzling.org (Postfix) with SMTP
        id 2E804944AF; Sat, 17 Apr 2004 19:43:34 +1000 (EST)
X-Message-Info: 7jzbcpjl6RND_LC_CHAR[1-3]QW/nxfFmfAbsNWUaxdMYK3HYc
Received: from drizzle ([48.88.16.164])
          by or32.bristle.hustle.destiny.lycos.com
          (InterMail vV.3.82.07.75 370-87-2-53-7-536568126) with ESMTP
          id <22087.MMNLA8509920.c9-mail.lessor.different.net.cable.rogers.com@oleander>
          for <exarkun@twistedmatrix.com>; Sun, 18 Apr 2004 05:33:58 -0500
Message-ID: <4670370065RND_LC_CHAR[1-5]12810o$60866140qt3$353j1pch3@backstop>
Reply-To: "Estelle Graves" <mucosa@wmconnect.com>
From: "Estelle Graves" <mucosa@wmconnect.com>
To: <exarkun@twistedmatrix.com>
Subject: Scare the banks away today..
Date: Sun, 18 Apr 2004 06:39:58 -0400
MIME-Version: 1.0 (produced by sportsmendelia 0.1)
Content-Type: multipart/alternative;
        boundary="--634550241884553"
X-Virus-Scanned: by amavisd-new-20030616-p7 (Debian) at puzzling.org
Status: RO

----634550241884553
Content-Type: text/html;
        charset="iso-8[4
""".strip()                     # This is important!  The message is different
                                # when it has a trailing newline.

class MessageTestCase(unittest.TestCase):
    """
    Test aspects of the L{twisted.mail.smtp.IMessage} implementation.
    """

    def testConnectionLost(self):
        fObj = test_grabber.AbortableStringIO()
        msg = mimepart.MIMEMessageReceiver(fObj, lambda: None)
        msg.connectionLost()
        self.failUnless(fObj.aborted, "Underlying message file not aborted on lost connection.")

