"""FastAPI server for hosting Plaid Link locally.

This module provides a simple local web server that:
1. Serves an HTML page with Plaid Link JS integration
2. Creates link tokens via /api/link-token endpoint
3. Exchanges public tokens via /api/exchange endpoint
4. Supports update mode for adding products to existing items
"""

import os
import uuid

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from loguru import logger
from pydantic import BaseModel

from budget_me.config import get_settings
from budget_me.crypto.token_encryption import TokenEncryption
from budget_me.db.engine import get_async_session
from budget_me.db.repos import ItemsRepo
from budget_me.plaid.link_flow import (
    add_liabilities_to_item,
    create_liabilities_upgrade_token,
    create_link_token,
    exchange_public_token,
)

app = FastAPI(title="Budget Me Link Server")


class ExchangeRequest(BaseModel):
    """Request model for token exchange."""

    public_token: str


@app.get("/", response_class=HTMLResponse)
def serve_link_page(
    mode: str | None = Query(None, description="Mode: 'update' for adding products"),
    item_id: str | None = Query(None, description="Item UUID for update mode"),
):
    """Serve HTML page with Plaid Link integration.

    This page:
    - Loads the Plaid Link JS SDK
    - Fetches a link token from /api/link-token
    - Initializes Plaid Link
    - On success, exchanges the public token via /api/exchange (or updates item for update mode)

    Args:
        mode: Optional mode - 'update' for adding products to existing item
        item_id: Item UUID (used in update mode)
    """
    # Determine page title and button text based on mode
    if mode == "update":
        page_title = "Add Liabilities Product"
        button_text = "Enable Liabilities Tracking"
        success_msg_prefix = "Liabilities product added!"
    else:
        page_title = "Link Your Bank Account"
        button_text = "Connect Bank Account"
        success_msg_prefix = "Success! Your bank account has been linked."

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Budget Me - {page_title}</title>
        <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                text-align: center;
            }}
            h1 {{
                color: #333;
            }}
            button {{
                background-color: #4CAF50;
                border: none;
                color: white;
                padding: 15px 32px;
                text-align: center;
                text-decoration: none;
                display: inline-block;
                font-size: 16px;
                margin: 4px 2px;
                cursor: pointer;
                border-radius: 4px;
            }}
            button:hover {{
                background-color: #45a049;
            }}
            .message {{
                margin-top: 20px;
                padding: 15px;
                border-radius: 4px;
            }}
            .success {{
                background-color: #d4edda;
                color: #155724;
            }}
            .error {{
                background-color: #f8d7da;
                color: #721c24;
            }}
        </style>
    </head>
    <body>
        <h1>{page_title}</h1>
        <p>Click the button below to securely connect {"additional products" if mode == "update" else "your bank account"} using Plaid.</p>
        <button id="link-button">{button_text}</button>
        <div id="message"></div>

        <script>
            const messageEl = document.getElementById('message');
            const linkButton = document.getElementById('link-button');
            const urlParams = new URLSearchParams(window.location.search);
            const mode = urlParams.get('mode');
            const itemId = urlParams.get('item_id');

            // Fetch link token and initialize Plaid Link
            linkButton.addEventListener('click', async () => {{
                try {{
                    // Build API URL with query params
                    let tokenUrl = '/api/link-token';
                    if (mode || itemId) {{
                        const params = new URLSearchParams();
                        if (mode) params.append('mode', mode);
                        if (itemId) params.append('item_id', itemId);
                        tokenUrl += '?' + params.toString();
                    }}

                    // Get link token
                    const tokenResponse = await fetch(tokenUrl, {{
                        method: 'POST'
                    }});
                    const tokenData = await tokenResponse.json();

                    if (!tokenData.link_token) {{
                        throw new Error('Failed to create link token');
                    }}

                    // Initialize Plaid Link
                    const handler = Plaid.create({{
                        token: tokenData.link_token,
                        onSuccess: async (public_token, metadata) => {{
                            console.log('Link success - mode:', mode);
                            console.log('Metadata:', metadata);

                            // Update mode - add liabilities to item
                            if (mode === 'update' && tokenData.item_id) {{
                                try {{
                                    const updateResponse = await fetch('/api/update-item', {{
                                        method: 'POST',
                                        headers: {{
                                            'Content-Type': 'application/json'
                                        }},
                                        body: JSON.stringify({{ item_id: tokenData.item_id }})
                                    }});

                                    const updateData = await updateResponse.json();

                                    if (updateData.success) {{
                                        messageEl.className = 'message success';
                                        messageEl.innerHTML = `
                                            <strong>{success_msg_prefix}</strong>
                                            <br>Item ID: ${{updateData.item_id}}
                                            <br>You can close this window and return to the CLI.
                                        `;
                                    }} else {{
                                        throw new Error(updateData.error || 'Update failed');
                                    }}
                                }} catch (error) {{
                                    messageEl.className = 'message error';
                                    messageEl.innerHTML = `<strong>Error:</strong> ${{error.message}}`;
                                }}
                            }}
                            // Standard mode - exchange token
                            else {{
                                try {{
                                    const exchangeResponse = await fetch('/api/exchange', {{
                                        method: 'POST',
                                        headers: {{
                                            'Content-Type': 'application/json'
                                        }},
                                        body: JSON.stringify({{ public_token }})
                                    }});

                                    const exchangeData = await exchangeResponse.json();

                                    if (exchangeData.success) {{
                                        messageEl.className = 'message success';
                                        messageEl.innerHTML = `
                                            <strong>{success_msg_prefix}</strong>
                                            <br>Item ID: ${{exchangeData.item_id}}
                                            <br>You can close this window and return to the CLI.
                                        `;
                                    }} else {{
                                        throw new Error(exchangeData.error || 'Exchange failed');
                                    }}
                                }} catch (error) {{
                                    messageEl.className = 'message error';
                                    messageEl.innerHTML = `<strong>Error:</strong> ${{error.message}}`;
                                }}
                            }}
                        }},
                        onExit: (err, metadata) => {{
                            if (err) {{
                                messageEl.className = 'message error';
                                messageEl.innerHTML = `<strong>Error:</strong> ${{err.error_message}}`;
                            }}
                        }},
                    }});

                    // Open Plaid Link
                    handler.open();
                }} catch (error) {{
                    messageEl.className = 'message error';
                    messageEl.innerHTML = `<strong>Error:</strong> ${{error.message}}`;
                }}
            }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# OAuth redirect URI - set via environment variable for HTTPS (e.g., ngrok)
# Example: PLAID_REDIRECT_URI=https://abc123.ngrok.io/oauth-callback
OAUTH_REDIRECT_URI = os.environ.get("PLAID_REDIRECT_URI")


@app.post("/api/link-token")
async def create_token(
    mode: str | None = Query(None, description="Mode: 'update' for adding products"),
    item_id: str | None = Query(None, description="Item UUID for update mode"),
):
    """Create a Plaid link token.

    Args:
        mode: Optional mode - 'update' for adding products to existing item
        item_id: Item UUID (required if mode=update)

    Returns:
        dict: Contains link_token for initializing Plaid Link
    """
    try:
        # Update mode - create upgrade token for existing item
        if mode == "update":
            if not item_id:
                raise HTTPException(
                    status_code=400, detail="item_id required for update mode"
                )

            # Load item from database
            async with get_async_session() as session:
                items_repo = ItemsRepo(session)
                item = await items_repo.get_by_id(uuid.UUID(item_id))

                if not item:
                    raise HTTPException(
                        status_code=404, detail=f"Item {item_id} not found"
                    )

                # Decrypt access token
                settings = get_settings()
                encryptor = TokenEncryption(settings.app_token_enc_key)
                access_token = encryptor.decrypt(item.access_token_enc)

                # Create upgrade token
                link_token = create_liabilities_upgrade_token(
                    access_token=access_token, redirect_uri=OAUTH_REDIRECT_URI
                )

                # Store item_id for later use in exchange
                return {"link_token": link_token, "item_id": item_id}

        # Standard mode - create new link token
        else:
            user_id = f"user_{uuid.uuid4().hex[:8]}"
            link_token = create_link_token(
                user_id=user_id, redirect_uri=OAUTH_REDIRECT_URI
            )
            return {"link_token": link_token}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error creating link token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/oauth-callback", response_class=HTMLResponse)
def oauth_callback():
    """Handle OAuth redirect from bank.

    After OAuth with the bank, the user is redirected here.
    This page reinitializes Plaid Link with the OAuth result.
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Budget Me - Completing Link</title>
        <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                text-align: center;
            }
            .message { margin-top: 20px; padding: 15px; border-radius: 4px; }
            .success { background-color: #d4edda; color: #155724; }
            .error { background-color: #f8d7da; color: #721c24; }
            .loading { background-color: #fff3cd; color: #856404; }
        </style>
    </head>
    <body>
        <h1>Completing Bank Connection...</h1>
        <div id="message" class="message loading">Processing OAuth callback...</div>

        <script>
            const messageEl = document.getElementById('message');

            async function completeOAuth() {
                try {
                    // Get a new link token for OAuth completion
                    const tokenResponse = await fetch('/api/link-token', { method: 'POST' });
                    const tokenData = await tokenResponse.json();

                    if (!tokenData.link_token) {
                        throw new Error('Failed to create link token');
                    }

                    // Reinitialize Plaid Link with the OAuth result
                    const handler = Plaid.create({
                        token: tokenData.link_token,
                        receivedRedirectUri: window.location.href,
                        onSuccess: async (public_token, metadata) => {
                            try {
                                const exchangeResponse = await fetch('/api/exchange', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ public_token })
                                });
                                const exchangeData = await exchangeResponse.json();

                                if (exchangeData.success) {
                                    messageEl.className = 'message success';
                                    messageEl.innerHTML = `
                                        <strong>Success!</strong> Your bank account has been linked.
                                        <br>Item ID: ${exchangeData.item_id}
                                        <br>You can close this window.
                                    `;
                                } else {
                                    throw new Error(exchangeData.error || 'Exchange failed');
                                }
                            } catch (error) {
                                messageEl.className = 'message error';
                                messageEl.innerHTML = '<strong>Error:</strong> ' + error.message;
                            }
                        },
                        onExit: (err) => {
                            if (err) {
                                messageEl.className = 'message error';
                                messageEl.innerHTML = '<strong>Error:</strong> ' + err.error_message;
                            }
                        },
                    });

                    handler.open();
                } catch (error) {
                    messageEl.className = 'message error';
                    messageEl.innerHTML = '<strong>Error:</strong> ' + error.message;
                }
            }

            // Start OAuth completion
            completeOAuth();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


class UpdateItemRequest(BaseModel):
    """Request model for item update."""

    item_id: str


@app.post("/api/update-item")
async def update_item(request: UpdateItemRequest):
    """Add liabilities product to an existing item.

    This endpoint is called after successful Plaid Link update flow.

    Args:
        request: Contains the item_id to update

    Returns:
        dict: Contains success status and item_id

    Raises:
        HTTPException: If update fails
    """
    try:
        # Add liabilities to item
        await add_liabilities_to_item(uuid.UUID(request.item_id))
        return {"success": True, "item_id": request.item_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})


@app.post("/api/exchange")
async def exchange_token(request: ExchangeRequest):
    """Exchange a public token for an access token.

    Args:
        request: Contains the public_token from Plaid Link

    Returns:
        dict: Contains success status and item_id

    Raises:
        HTTPException: If token exchange fails
    """
    try:
        # Generate a unique user ID for this session
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        result = await exchange_public_token(
            public_token=request.public_token, user_id=user_id
        )
        return {"success": True, "item_id": result["item_id"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})


def start_link_server(host: str = "localhost", port: int = 8080):
    """Start the Link server.

    Args:
        host: Host to bind to (default: localhost)
        port: Port to bind to (default: 8080)
    """
    uvicorn.run(app, host=host, port=port)
