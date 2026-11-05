"""Select official HTTPS archives on disposable Ubuntu 24.04 CI runners."""
from pathlib import Path
import re


def configure(source):
    original = source.read_text()
    if not re.search(r"^Suites:.*\bnoble\b", original, re.MULTILINE):
        raise RuntimeError("Expected Ubuntu 24.04 signed source configuration")
    blocks = []
    configured = 0
    for block in original.split("\n\n"):
        if re.search(r"^URIs:", block, re.MULTILINE):
            uri = ("https://security.ubuntu.com/ubuntu" if
                   re.search(r"^Suites:.*noble-security", block, re.MULTILINE) else
                   "https://archive.ubuntu.com/ubuntu")
            block, count = re.subn(r"^URIs:.*$", f"URIs: {uri}", block, flags=re.MULTILINE)
            if count != 1 or not re.search(r"^Signed-By:", block, re.MULTILINE):
                raise RuntimeError("Unexpected or unsigned Ubuntu source stanza")
            configured += 1
        blocks.append(block)
    if not configured:
        raise RuntimeError("No Ubuntu source URIs found")
    source.write_text("\n\n".join(blocks))
    return configured


if __name__ == "__main__":
    count = configure(Path("/etc/apt/sources.list.d/ubuntu.sources"))
    print(f"Configured {count} signed Ubuntu source stanzas with official HTTPS mirrors")
