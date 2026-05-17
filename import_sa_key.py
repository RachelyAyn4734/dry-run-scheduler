"""
Run once:
  python import_sa_key.py path\to\service-account-key.json

Appends the correct GCP_SERVICE_ACCOUNT_JSON line to secrets.toml.
"""
import json, pathlib, sys

def main():
    if len(sys.argv) < 2:
        print("Usage: python import_sa_key.py <path-to-service-account.json>")
        sys.exit(1)

    key_file = pathlib.Path(sys.argv[1])
    if not key_file.exists():
        print(f"File not found: {key_file}")
        sys.exit(1)

    data = json.loads(key_file.read_text(encoding="utf-8"))
    if data.get("type") != "service_account":
        print("ERROR: This is not a service_account JSON file.")
        print("  type found:", data.get("type"))
        sys.exit(1)

    # Validate key is complete
    pk = data.get("private_key", "")
    lines = pk.strip().split("\n")
    b64 = "".join(lines[1:-1])
    print(f"client_email : {data.get('client_email')}")
    print(f"private_key  : {len(pk)} chars, {len(b64)} base64 chars")
    if len(b64) < 1700:
        print("WARNING: private key looks too short — may be truncated!")
    else:
        print("private_key  : OK ✓")

    # Write as single-line JSON string into secrets.toml
    secrets_path = pathlib.Path(__file__).parent / ".streamlit" / "secrets.toml"
    single_line = json.dumps(data)

    # Remove old [gcp_service_account] block if present
    current = secrets_path.read_text(encoding="utf-8")
    lines_toml = current.splitlines()
    
    # Remove existing GCP_SERVICE_ACCOUNT_JSON line if exists
    lines_toml = [l for l in lines_toml if not l.startswith("GCP_SERVICE_ACCOUNT_JSON")]
    
    # Remove old [gcp_service_account] section
    new_lines = []
    skip = False
    for line in lines_toml:
        if line.strip() == "[gcp_service_account]":
            skip = True
            continue
        if skip and line.startswith("["):
            skip = False
        if not skip:
            new_lines.append(line)

    # Append the new single-line entry
    new_lines.append("")
    new_lines.append(f"GCP_SERVICE_ACCOUNT_JSON = '''{single_line}'''")
    new_lines.append("")

    secrets_path.write_text("\n".join(new_lines), encoding="utf-8")
    print(f"\n✅ Updated: {secrets_path}")
    print("Restart the Streamlit app to apply.")

if __name__ == "__main__":
    main()
