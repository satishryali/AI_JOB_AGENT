# Local credentials

Copy the repository-root `.env.example` to `.env` and fill in newly rotated credentials. Never commit `.env`, local environment variants, tokens, or database exports containing credentials.

Changing configuration does not rotate an existing database user's password. Update the password in the running PostgreSQL, Oracle, or Airflow service and then update the local configuration. Existing database volumes retain their original credentials; do not delete them to rotate a password.

Previously committed passwords remain in earlier commits and other branches. Rotate them wherever reused. History removal requires a coordinated rewrite of affected refs and cleanup of copies; this commit only removes the reported credentials from current main files.
