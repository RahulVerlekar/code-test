# hubspot.py

from fastapi import Request
import json
import secrets
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse
import httpx
import asyncio
import base64
import requests
from integrations.integration_item import IntegrationItem

from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

API_KEY = '44f50b48-acfe-452d-b277-d41cefc079f5'
CLIENT_ID = '835dc043-7dd0-494f-b2bb-f681ba74b96e'
CLIENT_SECRET = '6e4a8599-9eb8-405c-8d93-ede92ed816c7'
encoded_client_id_secret = base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()

REDIRECT_URI = 'http://localhost:8000/integrations/hubspot/oauth2callback'
authorization_url = f'https://app.hubspot.com/oauth/authorize?client_id=5f087fcd-5a08-496d-b27e-d30353c38aa3&redirect_uri=http://localhost:8000/integrations/hubspot/oauth2callback&scope=tickets%20oauth'

async def authorize_hubspot(user_id, org_id):
    state_data = {
        'state': secrets.token_urlsafe(32),
        'user_id': user_id,
        'org_id': org_id
    }
    encoded_state = json.dumps(state_data)
    await add_key_value_redis(f'hubspot_state:{org_id}:{user_id}', encoded_state, expire=600)

    return f'{authorization_url}&state={encoded_state}'

async def oauth2callback_hubspot(request: Request):
    if request.query_params.get('error'):
        raise HTTPException(status_code=400, detail=request.query_params.get('error'))
    code = request.query_params.get('code')
    encoded_state = request.query_params.get('state')
    state_data = json.loads(encoded_state)

    original_state = state_data.get('state')
    user_id = state_data.get('user_id')
    org_id = state_data.get('org_id')

    saved_state = await get_value_redis(f'hubspot_state:{org_id}:{user_id}')

    if not saved_state or original_state != json.loads(saved_state).get('state'):
        raise HTTPException(status_code=400, detail='State does not match.')

    async with httpx.AsyncClient() as client:
        response, _ = await asyncio.gather(
            client.post(
                'https://api.hubapi.com/oauth/v1/token',
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'client_id': CLIENT_ID,
                    'client_secret': CLIENT_SECRET,
                    'redirect_uri': REDIRECT_URI
                }, 
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8'
                }
            ),
            delete_key_redis(f'hubspot_state:{org_id}:{user_id}'),
        )

    await add_key_value_redis(f'hubspot_credentials:{org_id}:{user_id}', json.dumps(response.json()), expire=600)
    
    close_window_script = """
    <html>
        <script>
            window.close();
        </script>
    </html>
    """
    return HTMLResponse(content=close_window_script)

async def get_hubspot_credentials(user_id, org_id):
    credentials = await get_value_redis(f'hubspot_credentials:{org_id}:{user_id}')
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    credentials = json.loads(credentials)
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    await delete_key_redis(f'hubspot_credentials:{org_id}:{user_id}')

    return credentials

def create_integration_item_metadata_object(
        response_json
    ) -> IntegrationItem:
    
    integration_item_metadata = IntegrationItem(
        id = response_json.get('id', None),
        name = response_json.get('properties').get('subject', None) + "_" + response_json.get('properties').get('content'),
    )

    return integration_item_metadata

async def get_items_hubspot(credentials):
    """Aggregates all metadata relevant for a hubspot integration, Takes all the ticket data"""
    credentials = json.loads(credentials)
    response = requests.get(
        'https://api.hubapi.com/crm/v3/objects/tickets',
        headers={
            'Authorization': f'Bearer {credentials.get("access_token")}',
        },
    )

    if response.status_code == 200:
        results = response.json()['results']
        list_of_integration_item_metadata = []
        for result in results:
            list_of_integration_item_metadata.append(
                create_integration_item_metadata_object(result)
            )

        print(list_of_integration_item_metadata)
    return list_of_integration_item_metadata