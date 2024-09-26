import json
import boto3
import os
import logging
from botocore.exceptions import ClientError
import requests,re
from bs4 import BeautifulSoup as bs
import datetime


# Initialize the DynamoDB client
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DB'])
Pkey='url'
logging.getLogger().setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

#query for the existence of entry and subscribers
#update or add an entry if no record
def query_dynamodb_sns(url,email):
    try:
        current_price,title = price_crawl(url)
        if current_price==None or title==None:
            logging.error(f"failed to get current price from the website {url}.")
            raise ValueError(f"Failed to get price or title for {url}")
        
        # Get the item for url from DynamoDB
        response = table.get_item(
            Key={
                Pkey: url
            }
        )
        if 'Item' in response:
            item=response['Item']
            subscribers = item.get('subscribers',[])
            logging.info(f"Existing subscribers are {subscribers}")
            if email not in subscribers:
                update_dynamodb_subscribers(url,email)
                logging.info(f"Adding {email} to the subscribers list")
            else:
                update_sns_subscribers(item['SNS_ARN'],email)
                logging.info("The tracking item and subscribers are already in the DB.")
        else:
            logging.info(f"No entry found for {url}")
            sns_arn=create_sns(title,email)
            logging.info(f"Created a new SNS with arn: {sns_arn}")
            add_dynamodb_item(title,current_price,email,sns_arn,url)
            logging.info("Added new entry in DB.")
            
    except ClientError as e:
        logging.error(f"Error in query_dynamodb_sns: {e.response['Error']['Message']}")
        raise

def add_dynamodb_item(title,current_price, email,sns_arn,url):
    try:
        current_price_date = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        table.put_item(
            Item={
                "title": title,
                "url": url,
                "subscribers": [email],
                "max_price": current_price,
                "max_price_date": current_price_date,
                "lowest_price":current_price,
                "lowest_price_date": current_price_date,
                "SNS_ARN": sns_arn
                }
        )
        logging.info(f"Added new entry in the DB for {url}")
    except ClientError as e:
        logging.error(f"Error in add_dynamodb_item: {e.response['Error']['Message']}")
        raise

#update subscribers in dynamodb entry
def update_dynamodb_subscribers(url,email):
    #update dynamodb entry
    try:
        response = table.update_item(
            Key={
                Pkey: url
            },
            UpdateExpression="SET subscribers = list_append(if_not_exists(subscribers, :empty_list), :new_email)",
            ExpressionAttributeValues={
                ':empty_list': [],
                ':new_email': [email]
            },
            ReturnValues="UPDATED_NEW"
        )
        logging.info(f"Updated entry with new subscriber for {url}")
        return response['Attributes']
    except ClientError as e:
        logging.error(f"Error in update_dynamodb_subscribers: {e.response['Error']['Message']}")
        raise

#create a new sns with email as the first subscribers
def create_sns(title,subscriber):
    sns_client = boto3.client('sns')
    
    try:
        # Create the SNS topic
        topic_name = re.sub(r'[^a-zA-Z0-9-_]', '_', title)[:256]  # SNS topic name limitations
        response = sns_client.create_topic(Name=topic_name)
        topic_arn = response['TopicArn']
        logging.info(f"Created SNS topic: {title}")
        logging.info(f"Topic ARN: {topic_arn}")
        
        # Subscribe the email to the topic
        subscription = sns_client.subscribe(
            TopicArn=topic_arn,
            Protocol='email',
            Endpoint=subscriber
        )
        logging.info(f"Subscribed {subscriber} to the topic {title}.")
        return topic_arn
    except ClientError as e:
        logging.error(f"Error creating SNS topic or subscribing: {e}")
        raise

def update_sns_subscribers(sns_arn,email):
    sns_client = boto3.client('sns')
    try:
        response = sns_client.subscribe(
            TopicArn=sns_arn,
            Protocol='email',
            Endpoint=email
        )
        logging.info(f"Added subscriber {email} to SNS topic {sns_arn}")
    except ClientError as e:
        logging.error(f"Error in update_sns_subscribers: {e.response['Error']['Message']}")
        raise

def price_crawl(url):
    headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive'
    }
    try:
        response = requests.get(url, headers=headers)
        # Check if the request was successful
        response.raise_for_status()
        # Parse the HTML content
        soup = bs(response.text, 'html.parser')
        # Find the title element
        title_element = soup.find('span', class_='ux-textspans ux-textspans--BOLD')
        # Find the price element
        price_element = soup.find('span', class_='ux-textspans', string=lambda text: text and text.strip().startswith('US $'))
        if title_element and price_element:
            title = title_element.text.strip()
            # Extract the text and remove any unwanted characters
            price = price_element.text.strip().replace('US $', '').replace(',', '')
            return price, title
        else:
            logging.error(f"Failed to catch elements on the webpage {url}.")
            return None,None
    except requests.RequestException as e:
        logging.error(f"Error in price_crawl: {str(e)}")
        return None, None

def validate_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

def validate_url(url):
    pattern = r'^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$'
    if 'www.ebay.com' in url and re.match(pattern, url):
        return True
    return False

def lambda_handler(event, context):
    try:
        logging.info(f"Event: {json.dumps(event)}")
        #get url and email address from the api
        query_params = event.get('queryStringParameters', {})
        url = query_params.get('url')
        email = query_params.get('email')
        logging.info(f"Processing request for URL: {url} and email: {email}")
        if not validate_email(email):
            logging.error(f"Email {email} is invalid")
            return {
            'statusCode': 400,
            'headers': {
                'Access-Control-Allow-Origin': '*',  
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'OPTIONS,POST'  
            },
            'body': json.dumps({'error': 'email address is not valid.'})
        }
        if not validate_url(url):
            logging.error(f"URL {url} is invalid")
            return {
            'statusCode': 400,
            'headers': {
                'Access-Control-Allow-Origin': '*',  
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'OPTIONS,POST'  
            },
            'body': json.dumps({'error': 'url is not valid.'})
        }
        #Interact with dynamodb and sns
        query_dynamodb_sns(url,email)
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',  
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'OPTIONS,POST'  
            },
            'body': json.dumps({'message': 'Signed up successfully!'})
        }
    except KeyError as e:
        logging.error(f"Missing required parameter: {str(e)}")
        return {
            'statusCode': 400,
            'headers': {
                'Access-Control-Allow-Origin': '*',  
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'OPTIONS,POST'  
            },
            'body': json.dumps({'error': 'Missing required parameters'})
        }
    except Exception as e:
        logging.error(f"Unexpected error in lambda_handler: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',  
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'OPTIONS,POST'  
            },
            'body': json.dumps({'error': 'Internal server error'})
        }
    
    except ValueError as e:
        return {
            'statusCode': 400,
            'headers': {
                'Access-Control-Allow-Origin': '*',  
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'OPTIONS,POST'  
            },
            'body': json.dumps({'error': str(e)})
        }