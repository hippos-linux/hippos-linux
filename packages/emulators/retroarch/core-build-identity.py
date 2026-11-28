"""Usage: core-build-identity.py <core.so>

Prints a hash of a libretro core with its build dates, times and GNU build ID blanked,
so two nightly builds of the same source print the same value.
"""

import hashlib
import re
import sys

BUILD_STAMP = re.compile(
    rb'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [ 0-3][0-9] [0-9]{4}'
    rb'|[0-9]{4}-[01][0-9]-[0-3][0-9](?:T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z?)?'
    rb'|[0-2][0-9]:[0-5][0-9]:[0-5][0-9]'
)
GNU_BUILD_ID = re.compile(rb'(\x04\x00\x00\x00\x14\x00\x00\x00\x03\x00\x00\x00GNU\x00).{20}', re.DOTALL)


def blank(match: re.Match) -> bytes:
    return match.group(1) + b'\0' * 20 if match.re is GNU_BUILD_ID else b'\0' * len(match.group())


core = open(sys.argv[1], 'rb').read()
core = GNU_BUILD_ID.sub(blank, BUILD_STAMP.sub(blank, core))
print(hashlib.sha256(core).hexdigest())
