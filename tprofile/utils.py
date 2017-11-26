from contextlib import contextmanager
import logging

from tornado import gen

logger = logging.getLogger(__name__)


@contextmanager
def log_errors(pdb=False):
    try:
        yield
    except (gen.Return):
        raise
    except Exception as e:
        try:
            logger.exception(e)
        except TypeError:  # logger becomes None during process cleanup
            pass
        if pdb:
            import pdb
            pdb.set_trace()
        raise
