"""Fetch one scoped managed secret into a root-private tmpfs directory; never print values."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote


def materialize(values, directory):
    expected = {"postgres_password", "app_password", "migration_password", "redis_password", "session_secret"}
    if set(values) != expected:
        raise ValueError("Managed secret must contain exactly the documented runtime keys")
    if any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", value)
           for value in values.values()):
        raise ValueError("Runtime secrets must be 32–128 URL-safe characters")
    files = {**values,
             "database_url": f"postgresql+psycopg://chubby_app:{quote(values['app_password'], safe='')}@db:5432/chubby",
             "migration_database_url": f"postgresql+psycopg://chubby_migrator:{quote(values['migration_password'], safe='')}@db:5432/chubby",
             "redis_url": f"redis://:{quote(values['redis_password'], safe='')}@redis:6379/0"}
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=False, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_uid != os.geteuid():
        raise ValueError("Secret directory must be owned by the invoking user and not a symlink")
    directory.chmod(0o700)
    for name, value in files.items():
        # Fail instead of overwriting live secrets or following a symlink.
        with (directory / name).open("x") as output:
            output.write(value)
        (directory / name).chmod(0o444)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret-id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    result = subprocess.run(["aws", "secretsmanager", "get-secret-value", "--secret-id", args.secret_id,
                             "--region", args.region, "--query", "SecretString", "--output", "text",
                             "--no-cli-pager"], check=True, capture_output=True, text=True)
    materialize(json.loads(result.stdout), args.directory)
    print("Managed secrets materialized; no secret values logged.")


if __name__ == "__main__":
    main()
