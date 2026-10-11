#!/usr/bin/env python3
"""Record provider-confirmed absence after artifact download. No deletion API."""
import argparse
import json
from cloud_records import record_termination


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',required=True)
    p.add_argument('--provider-snapshot',required=True)
    p.add_argument('--artifact-download-evidence',required=True)
    a=p.parse_args()
    record=record_termination(a.campaign,a.provider_snapshot,a.artifact_download_evidence)
    print(json.dumps(record,indent=2))
