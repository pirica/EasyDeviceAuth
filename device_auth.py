import asyncio
import json
import os

import aiohttp
import chromedriver_autoinstaller
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

DEVICE_AUTH_FILENAME = 'device_auths.json'
DRIVER_DOWNLOAD_URL = 'https://github.com/mozilla/geckodriver/releases/download/v0.28.0/geckodriver-v0.28.0-win64.zip'
IOS_TOKEN = 'MzQ0NmNkNzI2OTRjNGE0NDg1ZDgxYjc3YWRiYjIxNDE6OTIwOWQ0YTVlMjVhNDU3ZmI5YjA3NDg5ZDMxM2I0MWE='
driver = webdriver.Chrome


def download_driver():
    print('Installing drivers...')
    #try:
    chromedriver_autoinstaller.install(True)
    #except:
    #    print('Chrome is not installed. Please install it and try again.')
    #    return False
    return True


def get_device_auth_details():
    if os.path.isfile(DEVICE_AUTH_FILENAME):
        with open(DEVICE_AUTH_FILENAME, 'r') as fp:
            return json.load(fp)
    return {}


def store_device_auth_details(email, details):
    existing = get_device_auth_details()
    existing[email] = details

    with open(DEVICE_AUTH_FILENAME, 'w') as fp:
        json.dump(existing, fp)


async def get_device_auth(email, code):
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'basic {IOS_TOKEN}',
    }
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'includePerms': False,
    }
    auth_code_url = 'https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token'
    async with aiohttp.ClientSession() as session:
        response = await session.post(auth_code_url, data=payload, headers=headers)
    if response.status >= 400:
        try:
            error = await response.json()
        except ValueError:
            error = {}
        error_code = error.get('errorCode', 'Not provided')
        error_message = error.get('errorMessage', 'Not provided')

        if error_code == 'errors.com.epicgames.account.oauth.authorization_code_not_found':
            print(f'Invalid authorization code found for {email}. Skipping account...')
            return None
        else:
            raise Exception(
                f'An unexpected error occurred while logging in with authorization code. '
                f'Code: {error_code} '
                f'Message: {error_message}'
            )

    data = await response.json()
    account_id = data['account_id']
    access_token = data['access_token']
    display_name = data['displayName']

    headers = {'Authorization': f'bearer {access_token}'}
    device_auth_url = \
        f'https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}/deviceAuth'
    async with aiohttp.ClientSession() as session:
        response = await session.post(device_auth_url, headers=headers)
    if response.status >= 400:
        try:
            error = await response.json()
        except ValueError:
            error = {}
        error_code = error.get('errorCode', 'Not provided')
        error_message = error.get('errorMessage', 'Not provided')

        raise Exception(f'An unexpected error occurred while generating device auth. '
                        f'Code: {error_code} '
                        f'Message: {error_message}')

    data = await response.json()
    return {'device_id': data['deviceId'], 'account_id': data['accountId'], 'secret': data['secret']}


def get_code(email, password):
    session_driver = driver()
    session_driver.set_window_size(600, 800)
    session_driver.get('https://www.epicgames.com/id/login/epic')
    WebDriverWait(session_driver, 30).until(EC.presence_of_element_located((By.ID, 'email')))
    email_input = session_driver.find_element_by_id('email')
    email_input.send_keys(email)
    password_input = session_driver.find_element_by_id('password')
    password_input.send_keys(password)
    WebDriverWait(session_driver, 30).until(EC.element_to_be_clickable((By.ID, 'sign-in')))
    signin_button = session_driver.find_element_by_id('sign-in')
    signin_button.click()
    print('Wait for entering 2-FA code and/or solving captcha...')
    WebDriverWait(session_driver, 60 * 60).until(EC.url_matches('https://www.epicgames.com/account/personal'))
    session_driver.get('https://www.epicgames.com/id/api/redirect?clientId=3446cd72694c4a4485d81b77adbb2141&responseType=code')
    print(session_driver.page_source)
    WebDriverWait(session_driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, 'pre')))
    pre = session_driver.find_element_by_tag_name("pre").text
    session_driver.close()
    url = json.loads(pre)['redirectUrl']
    code = url.split('?code=')[1]
    return code


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    success = download_driver()
    if not success:
        exit(1)
    print('Load credentials...')
    if not os.path.isfile('credentials.json'):
        with open('credentials.json', 'w') as fp:
            json.dump({}, fp)
    with open('credentials.json') as f:
        credentials = json.load(f)
    print(f'Found {len(credentials)} accounts.')
    for email, password in credentials.items():
        print(f'Getting authorization code for {email}...')
        code = get_code(email, password)
        print(f'Generating device auth for {email}')
        device_auth = loop.run_until_complete(get_device_auth(email, code))
        store_device_auth_details(email, device_auth)
        print(f'Successfully generated device auth for {email}')
    print('Finished generating device auths.')
