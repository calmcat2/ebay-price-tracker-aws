import json
import boto3
import os
import logging
import requests
import re
from bs4 import BeautifulSoup as bs
import datetime
from botocore.exceptions import ClientError

# Initialize services
dynamodb = boto3.resource('dynamodb')
sns_client = boto3.client('sns')
table = dynamodb.Table(os.environ['DB'])
PRIMARY_KEY = 'url'

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

class DynamoDBError(Exception):
    pass

class SNSError(Exception):
    pass

def query_dynamodb_sns(url, email):
    try:
        current_price, title = price_crawl(url)
        if not current_price or not title:
            logger.error(f"Failed to get current price/title from the website {url}.")
            raise ValueError(f"Failed to get price or title for {url}")

        response = table.get_item(Key={PRIMARY_KEY: url})

        if 'Item' in response:
            logger.info("Found an entry in DB.")
            item = response['Item']
            subscribers = item.get('subscribers', [])
            logger.info(f"Existing subscribers are {subscribers}")

            if email not in subscribers:
                update_dynamodb_subscribers(url, email)
                update_sns_subscribers(item['SNS_ARN'], email)
                logger.info(f"Adding {email} to the subscribers list")
            else:
                update_sns_subscribers(item['SNS_ARN'], email)
                logger.info("The tracking item and subscribers are already in the DB. Resent a subscription confirmation email to {email}.")
        else:
            logger.info(f"No entry found for {url}. Creating a new one.")
            sns_arn = create_sns(title, email)
            logger.info(f"Created a new SNS with arn: {sns_arn}")
            add_dynamodb_item(title, current_price, email, sns_arn, url)
            logger.info("Added a new entry in DB.")

    except ClientError as e:
        logger.error(f"Error in querying dynamodb: {e.response['Error']['Message']}")
        raise DynamoDBError('Failed to query or update DynamoDB')

def add_dynamodb_item(title, current_price, email, sns_arn, url):
    try:
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        item = {
            "title": title,
            "url": url,
            "subscribers": [email],
            "max_price": current_price,
            "max_price_date": current_time,
            "lowest_price": current_price,
            "lowest_price_date": current_time,
            "SNS_ARN": sns_arn
        }
        table.put_item(Item=item)
        logger.info(f"Added new entry in the DB for {url}")
    except ClientError as e:
        logger.error(f"Error in add_dynamodb_item: {e.response['Error']['Message']}")
        raise DynamoDBError('Failed to add entry to DynamoDB.')

def update_dynamodb_subscribers(url, email):
    try:
        response = table.update_item(
            Key={PRIMARY_KEY: url},
            UpdateExpression="SET subscribers = list_append(if_not_exists(subscribers, :empty_list), :new_email)",
            ExpressionAttributeValues={
                ':empty_list': [],
                ':new_email': [email]
            },
            ReturnValues="UPDATED_NEW"
        )
        logger.info(f"Updated entry with new subscriber for {url}")
        return response['Attributes']
    except ClientError as e:
        logger.error(f"Error in updating dynamodb: {e.response['Error']['Message']}")
        raise DynamoDBError('Failed to update subscribers in DynamoDB')

def create_sns(title, subscriber):
    try:
        topic_name = re.sub(r'[^a-zA-Z0-9-_]', '_', title)[:256]
        response = sns_client.create_topic(Name=topic_name)
        topic_arn = response['TopicArn']
        
        logger.info(f"Created SNS topic: {title}")
        logger.info(f"Topic ARN: {topic_arn}")
        
        sns_client.subscribe(
            TopicArn=topic_arn,
            Protocol='email',
            Endpoint=subscriber
        )
        
        logger.info(f"Subscribed {subscriber} to the topic {title}.")
        return topic_arn
    except ClientError as e:
        logger.error(f"Error creating SNS topic or subscribing: {e}")
        raise SNSError('Failed to create SNS topic or subscribe')

def update_sns_subscribers(sns_arn, email):
    try:
        sns_client.subscribe(
            TopicArn=sns_arn,
            Protocol='email',
            Endpoint=email
        )
        logger.info(f"Added subscriber {email} to SNS topic {sns_arn}")
    except ClientError as e:
        logger.error(f"Error in updating sns subscribers: {e.response['Error']['Message']}")
        raise SNSError('Failed to update SNS subscribers')

def price_crawl(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = bs(response.text, 'html.parser')
        
        title_element = soup.find('span', class_='ux-textspans ux-textspans--BOLD')
        price_element = soup.find('span', class_='ux-textspans', string=lambda text: text and text.strip().startswith('US $'))
        logger.info(f'title: {title_element}  price: {price_element}')
        if title_element and price_element:
            title = title_element.text.strip()
            price = price_element.text.strip().replace('US $', '').replace(',', '').split('/')[0]
            return price, title
        else:
            logger.error(f"Failed to catch elements on the webpage {url}.")
            return None, None
    except requests.RequestException as e:
        logger.error(f"Error in price_crawl: {str(e)}")
        return None, None

# def validate_email(email):
#     pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
#     return re.match(pattern, email) is not None

# def validate_url(url):
#     pattern = r'^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$'
#     return 'www.ebay.com' in url and re.match(pattern, url)

def create_response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': 'https://app1.maxinehe.top',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'OPTIONS,POST'
        },
        'body': json.dumps(body)
    }

def lambda_handler(event, context):
    try:
        logger.info(f"Event: {json.dumps(event)}")
        query_params = event.get('queryStringParameters', {})
        url = query_params.get('url')
        email = query_params.get('email')
        
        logger.info(f"Processing request for URL: {url} and email: {email}")
        
        # if not validate_email(email):
        #     logger.error(f"Email {email} is invalid")
        #     return create_response(400, {'error': 'email address is not valid.'})
        
        # if not validate_url(url):
        #     logger.error(f"URL {url} is invalid")
        #     return create_response(400, {'error': 'url is not valid.'})
        
        query_dynamodb_sns(url, email)
        return create_response(200, {'message': 'Signed up successfully!'})
    
    except KeyError as e:
        logger.error(f"Missing required parameter: {str(e)}")
        return create_response(400, {'error': 'Missing required parameters'})
    except (DynamoDBError, SNSError) as e:
        return create_response(500, {'error': str(e)})
    except Exception as e:
        logger.error(f"Unexpected error in lambda_handler: {str(e)}")
        return create_response(500, {'error': 'Internal server error'})