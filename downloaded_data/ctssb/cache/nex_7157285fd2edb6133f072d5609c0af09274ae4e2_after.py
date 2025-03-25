from contextlib import contextmanager
from collections import deque

from ..reader import EndOfFile
from ..utils import NoSuchControlSequence


class ExpectedParsingError(Exception):
    pass


class ExhaustedTokensError(Exception):
    pass


end_tag = '$end'


def is_end_token(t):
    return hasattr(t, 'name') and t.name == end_tag and t.value == end_tag


class GetBuffer:

    def __init__(self, getter, initial=None):
        self.queue = deque()
        if initial is not None:
            self.queue.extend(initial)
        self.getter = getter

    def __iter__(self):
        return self

    def __next__(self):
        while not self.queue:
            self.queue.extend(self.getter())
        return self.queue.popleft()


@contextmanager
def safe_chunk_grabber(banisher, *args, **kwargs):
    c = ChunkGrabber(banisher, *args, **kwargs)
    yield c
    if c.out_queue.queue:
        raise ValueError(f'Finished with chunk grabber but still tokens on '
                         f'output queue: {c.out_queue.queue}')


class ChunkGrabber(object):

    def __init__(self, banisher, parser, initial=None):
        self.banisher = banisher
        self.parser = parser

        # Processing input tokens might return many tokens, so
        # we store them in a buffer.
        self.out_queue = GetBuffer(getter=banisher.get_next_output_list,
                                   initial=initial)

    def get_chunk(self):
        # Want to extend the queue-to-be-parsed one token at a time,
        # so we can break as soon as we have all we need.
        chunk_token_queue = deque()
        # Get enough tokens to grab a parse-chunk. We know to stop adding tokens
        # when we see a switch from failing because we run out of tokens
        # (ExhaustedTokensError) to an actual syntax error
        # (ExpectedParsingError).
        # We keep track of if we have parsed, just for checking for weird
        # situations.
        have_parsed = False
        while True:
            try:
                t = next(self.out_queue)
            except EndOfFile:
                # If we get an EndOfFile, and we have just started trying to
                # get a parse-chunk, we are done, so just propagate the
                # exception to wrap things up.
                if not chunk_token_queue:
                    raise
                # If we get an EndOfFile and we have already parsed, we need to
                # return this parse-chunk, then next time round we will be
                # done.
                elif have_parsed:
                    break
                # If we get to the end of the file and we have a chunk queue
                # that can't be parsed, something is wrong.
                else:
                    import pdb; pdb.set_trace()
                    pass
            # If we get an expansion error, it might be because we need to
            # act on the chunk we have so far first.
            except NoSuchControlSequence as e:
                # This is only possible if we have already parsed the chunk-so-
                # far.
                if have_parsed:
                    break
                # Otherwise, indeed something is wrong.
                else:
                    raise
            except Exception as e:
                import pdb; pdb.set_trace()
                raise
            chunk_token_queue.append(t)
            try:
                chunk = self.parser.parse(iter(chunk_token_queue))
            # If we got a syntax error, this should mean we have spilled over
            # into parsing the next chunk.
            except ExpectedParsingError:
                # If we have already parsed a chunk, then we use this as our
                # result.
                if have_parsed:
                    # We got one token of fluff due to extra read, to make the
                    # parse queue not-parse. So put it back on the buffer.
                    self.out_queue.queue.appendleft(chunk_token_queue.pop())
                    break
                # If we have not yet parsed, then something is wrong.
                else:
                    import pdb; pdb.set_trace()
                    raise
            except ExhaustedTokensError:
                # Carry on getting more tokens, because it seems we can.
                pass
            else:
                # Implemented in our modified version of rply, we annotate the
                # output token to indicate whether the only action from the
                # current parse state could be to end. In this case, we do not
                # bother adding another token, and just return the chunk.
                # This reduces the number of cases where we expand too far, and
                # must handle bad handling of the post- chunk tokens caused by
                # not acting on this chunk.
                if chunk._could_only_end:
                    break
                have_parsed = True
        # We might want to reverse the composition of terminal tokens we just
        # did in the parser, so save the bits in a special place.
        chunk._terminal_tokens = list(chunk_token_queue)
        return chunk

    def clean_up(self):
        self.banisher.instructions.replace_tokens_on_input(self.out_queue.queue)
