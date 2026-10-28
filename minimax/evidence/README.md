# Evidence directory

This initial package intentionally does NOT contain invented MiniMax, seekdb, or PowerContext success traces.

Run `bash scripts/full_demo_wsl.sh` with real credentials and installed dependencies. The runner will write:

- `01_scope.json` ... `15_submission_audit.json`, which show the exact steps performed;
- `database_ingest.json`, `database_last_query.json`: real SQL and returned indexed rows;
- `state_last_write.json`, `state_last_read.json`: actual PowerContext responses;
- `context_latest.json`: complete model context with provenance;
- `model_last_success.json` and `runs/*_minimax_live/*`: real MiniMax prompt/response and paired code diff;
- `runs/*_tests/*`: test commands, exit codes, code version, test hashes, stdout and stderr.

The runtime database under `../runtime` and `.env` are not competition artifacts and must not be committed. Commit model logs only after a successful real run; scrub any accidental secrets if customizing the example. No private reasoning chains are requested or recorded.
