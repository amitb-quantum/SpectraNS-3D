"""Conservative disk model for the existing six-state retention schedule."""
import math,os
from pathlib import Path

DISK_GB = 120
MAX_HOURLY_USD = "4.5"
STATE_BYTES = 10899947904
MAX_RAW_STATES = 6
ARCHIVE_BYTES_UPPER = 10910000000
SMALL_ARTIFACT_BYTES_RESERVE = 2000000000
FREE_SPACE_MARGIN = 1.20

def disk_requirement():
    # Coarse and exploration each retain two regular states plus a terminal.
    # Write-before-prune reaches three regular states; the terminal replaces
    # that temporary third state. Fine/reload produce no field checkpoints.
    runtime = MAX_RAW_STATES*STATE_BYTES + ARCHIVE_BYTES_UPPER + SMALL_ARTIFACT_BYTES_RESERVE
    return dict(requested_disk_GB=DISK_GB,full_state_bytes=STATE_BYTES,
                maximum_raw_states=MAX_RAW_STATES,runtime_bytes_upper=runtime,
                required_free_bytes=math.ceil(FREE_SPACE_MARGIN*runtime),
                free_space_margin=FREE_SPACE_MARGIN,
                scope="Available space after setup; image and installed packages already occupy disk.")

def check_free_space(path):
    path=Path(path)
    usage=os.statvfs(path)
    available=usage.f_bavail*usage.f_frsize
    record=dict(disk_requirement(),path=str(path),available_bytes=available,
                filesystem_total_bytes=usage.f_blocks*usage.f_frsize)
    record["fits"]=available>=record["required_free_bytes"]
    return record
