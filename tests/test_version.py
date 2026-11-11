import re

import uptime_lite


def test_version_is_semver_like() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", uptime_lite.__version__)
