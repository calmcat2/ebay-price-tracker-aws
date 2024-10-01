import pytest
import requests

lambda_url = "https://5cga67cqkyksz7lqcuaupdf6cu0evtuz.lambda-url.us-east-1.on.aws/"
api_url="https://5cga67cqkyksz7lqcuaupdf6cu0evtuz.lambda-url.us-east-1.on.aws/"
url=api_url

def print_response(response):
    print(f"Status Code: {response.status_code}")
    print(f"Response JSON: {response.json()}")
    print("---")

def test_lambda_handler_success():
    params = {
        "url": "https://www.ebay.com/itm/133058473014",
        "email": "me@maxinehe.top"
    }
    response = requests.get(url, params=params)
    print_response(response)
    assert response.status_code == 200
    assert response.json() == {'message': 'Signed up successfully!'}

def test_lambda_handler_missing_key1():
    params = {
        "url": "",
        "email": "me@maxinehe.top"
    }
    response = requests.get(url, params=params)
    print_response(response)
    assert response.status_code == 400
    assert response.json() == {'error': 'Invalid URL'}

def test_lambda_handler_missing_key2():
    params = {
        "url": "https://www.ebay.com/itm/133058473014",
        "email": ""
    }
    response = requests.get(url, params=params)
    print_response(response)
    assert response.status_code == 400
    assert response.json() == {'error': 'Invalid email address'}

def test_lambda_handler_bad_url():
    params = {
        "url": "https://www.amazon.com/itm/133058473014",
        "email": "me@maxinehe.top"
    }
    response = requests.get(url, params=params)
    print_response(response)
    assert response.status_code == 400
    assert response.json() == {'error': 'Invalid URL'}

def test_lambda_handler_unexist_url():
    params = {
        "url": "https://www.ebay.com/itm/1",
        "email": "me@max.com"
    }
    response = requests.get(url, params=params)
    print_response(response)
    assert response.status_code == 400
    assert 'error' in response.json()=={'error': 'Failed to get price or title for https://www.ebay.com/itm/1'}
