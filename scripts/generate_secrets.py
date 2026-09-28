#!/usr/bin/env python3
"""Generate .streamlit/secrets.toml from environment variables.

This script is run at startup on Render to populate Streamlit's secrets.toml
from environment variables configured in the Render dashboard.
"""

import os
from pathlib import Path


def generate_secrets_toml():
    """Generate .streamlit/secrets.toml from environment variables."""
    # Get environment variables
    redirect_uri = os.environ.get("AUTH_REDIRECT_URI", "")
    cookie_secret = os.environ.get("AUTH_COOKIE_SECRET", "")
    google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    # Validate required variables
    if not all([redirect_uri, cookie_secret, google_client_id, google_client_secret]):
        print("Warning: Missing required OAuth environment variables")
        print(f"  AUTH_REDIRECT_URI: {'set' if redirect_uri else 'missing'}")
        print(f"  AUTH_COOKIE_SECRET: {'set' if cookie_secret else 'missing'}")
        print(f"  GOOGLE_CLIENT_ID: {'set' if google_client_id else 'missing'}")
        print(f"  GOOGLE_CLIENT_SECRET: {'set' if google_client_secret else 'missing'}")
        return

    # Create .streamlit directory if it doesn't exist
    streamlit_dir = Path.home() / ".streamlit"
    streamlit_dir.mkdir(parents=True, exist_ok=True)

    # Generate secrets.toml content
    secrets_content = f'''# Auto-generated from environment variables
# Do not edit manually - this file is regenerated on each deployment

[auth]
redirect_uri = "{redirect_uri}"
cookie_secret = "{cookie_secret}"

[auth.google]
client_id = "{google_client_id}"
client_secret = "{google_client_secret}"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
'''

    # Write secrets.toml
    secrets_file = streamlit_dir / "secrets.toml"
    secrets_file.write_text(secrets_content)
    print(f"Generated {secrets_file} from environment variables")


if __name__ == "__main__":
    generate_secrets_toml()
