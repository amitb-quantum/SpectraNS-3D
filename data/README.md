# Local original inputs

`original/` contains the supplied ZIP, two TGZs and their exact extracted
contents. It is Git-ignored because it includes historical instance metadata.
The hash inventory is `configs/original_manifest.json`, with paths relative
to `data/original/`. Run `python scripts/verify_provenance.py` to verify it.

After a fresh clone, copy `ns_regularity_upgrade_v1.zip`,
`ns_audit_package.tgz`, and `ns_campaign_results.tgz` into `data/original/`,
then run `python scripts/restore_inputs.py`. Tests use a small tracked
original-solver fixture and do not need these archives.
