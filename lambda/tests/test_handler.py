import sys
import os

# Add the src directory to the Python path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
DB="price_tracker_v1"

from handler import lambda_handler

def test_lambda_handler_success():
    event = {
        "queryStringParameters": {
            "url": "https://www.ebay.com/itm/133058473014",
            "email": "me@maxinehe.top"
        }
    }
    response = lambda_handler(event, None)
    assert response == {'message': 'Signed up successfully!'}

def test_lambda_handler_missing_key1():
    event = {
        "queryStringParameters": {
            "url": "",
            "email": "me@maxinehe.top"
        }
    }
    response = lambda_handler(event, None)
    assert response == {'error': 'Missing required parameters'}

def test_lambda_handler_missing_key2():
    event = {
        "queryStringParameters": {
            "url": "https://www.ebay.com/itm/133058473014",
            "email": ""
        }
    }
    response = lambda_handler(event, None)
    assert response == {'error': 'Missing required parameters'}

def test_lambda_handler_bad_url():
    event = {
        "queryStringParameters": {
                "url": "https://www.amazon.com/itm/133058473014",
                "email": "me@maxinehe.top"
            }
    }
    response = lambda_handler(event, None)
    assert response == {'error': 'url is not valid.'}
def test_lambda_handler_bad_url():
    event = {
        "queryStringParameters": {
                "url": "https://www.ebay.com/itm/1",
                "email": "me@max"
            }
    }
    response = lambda_handler(event, None)
    assert response == {'error': 'Failed to get price or title for https://www.ebay.com/itm/1'}