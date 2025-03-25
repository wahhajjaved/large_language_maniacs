import os
import hashlib
import random
import time


PROJECT_DIR = os.path.realpath(os.path.curdir)

# Use the system PRNG if possible
# https://github.com/django/django/blob/stable/1.9.x/django/utils/crypto.py#L18-L26
try:
    random = random.SystemRandom()
    using_sysrandom = True
except NotImplementedError:
    import warnings
    warnings.warn('A secure pseudo-random number generator is not available '
                  'on your system. Falling back to Mersenne Twister.')
    using_sysrandom = False


def get_random_string(length=12,
                      allowed_chars='abcdefghijklmnopqrstuvwxyz'
                                    'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'):
    """
    Returns a securely generated random string.
    The default length of 12 with the a-z, A-Z, 0-9 character set returns
    a 71-bit value. log_2((26+26+10)^12) =~ 71 bits
    https://github.com/django/django/blob/stable/1.9.x/django/utils/crypto.py#L54-L77
    """
    if not using_sysrandom:
        # This is ugly, and a hack, but it makes things better than
        # the alternative of predictability. This re-seeds the PRNG
        # using a value that is hard for an attacker to predict, every
        # time a random string is required. This may change the
        # properties of the chosen random sequence slightly, but this
        # is better than absolute predictability.
        random.seed(
            hashlib.sha256(
                ("%s%s%s" % (
                    random.getstate(),
                    time.time(),
                    settings.SECRET_KEY)).encode('utf-8')
            ).digest())
    return ''.join(random.choice(allowed_chars) for i in range(length))


def generate_secret_key(project_directory):

    env_path = os.path.join(project_directory, '.env_example')

    with open(env_path) as f:
        env_file = f.read()

    chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'

    env_file = env_file.replace('KEY_PLACE', get_random_string(50, chars))
    env_file = env_file.replace('DEBUG_VALUE', str(True))

    with open(env_path, 'w') as f:
        f.write(env_file)


generate_secret_key(PROJECT_DIR)
