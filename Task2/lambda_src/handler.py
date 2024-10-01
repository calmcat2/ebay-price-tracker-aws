import json
import boto3
import os
import logging
from botocore.exceptions import ClientError
from bs4 import BeautifulSoup as bs
import requests
import datetime

#logging settings
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize the DynamoDB client
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DB'])

class WebScrapingError(Exception):
    pass
class DynamoDBError(Exception):
    pass
class SNSError(Exception):
    pass

def price_crawl(url):
    headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive'
    }
    try:
        # header is added to prevent robot blocking
        response = requests.get(url, headers=headers)
        # Check if the request was successful
        response.raise_for_status()
        # Parse the HTML content
        soup = bs(response.text, 'html.parser')
        logger.info(f"Loading webpage {url}...")
        logger.info("Looking for Item title...")
        # Find the title element
        title_element = soup.find('span', class_='ux-textspans ux-textspans--BOLD')
        # Find the price element
        logger.info("Looking for Item price...")
        price_element = soup.find('span', class_='ux-textspans', string=lambda text: text and text.strip().startswith('US $'))
        if title_element and price_element:
            title = title_element.text.strip()
            # Extract the text and remove any unwanted characters
            price = price_element.text.strip().replace('US $', '').replace(',', '').split('/')[0]
            return price, title
        else:
            return None,None
    except requests.RequestException as e:
        raise WebScrapingError(f"Error in price_crawl: {str(e)}")


#Read from dynamodb
def read_dynamodb():
    items = []

    try:
        # Define the attributes you want to retrieve
        projection_expression = "#u, max_price, lowest_price, lowest_price_date, SNS_ARN"
        expression_attribute_names = {"#u": "url"}
        
        # Scan the table with ProjectionExpression
        response = table.scan(
            ProjectionExpression=projection_expression,
            ExpressionAttributeNames=expression_attribute_names
        )
        items.extend(response['Items'])

        # If there are more items, keep scanning
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                ProjectionExpression=projection_expression,
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response['Items'])
        
        logger.info(f"Successfully read {len(items)} items from the table.")
        return items

    except ClientError as e:
        logger.error(f"Error reading from DynamoDB table {table}: {e}")
        return None

#Update dynamodb
def update_dynamodb_lowest_price(url,lowest_price):

    #update dynamodb entry
    lowest_price_date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        response = table.update_item(
            Key={
                'url': url
            },
            UpdateExpression='SET  lowest_price= :val1,  lowest_price_date= :val2',
            ExpressionAttributeValues={
                ':val1': lowest_price,
                ':val2': lowest_price_date
            },
            ReturnValues="UPDATED_NEW"
        )
        logger.info(f"Updated lowest price for {url}")
        return response['Attributes']
    except ClientError as e:
        raise DynamoDBError(f"Error in update_dynamodb_subscribers: {e.response['Error']['Message']}")
        

def publish_sns(sns_arn, subject, body):
    # Create an SNS client
    sns_client = boto3.client('sns')

    try:
        # Publish the message
        response = sns_client.publish(
            TopicArn=sns_arn,
            Subject=subject,
            Message=body
        )
        
        # Log the success
        logger.info(f"Message published to SNS topic {sns_arn}")
        # logger.info(f"Message ID: {response['MessageId']}")
        
        # Return the message ID
        return response['MessageId']

    except ClientError as e:
        # Log the error
        raise SNSError(f"Error publishing message to SNS topic {sns_arn}: {e}")

def lambda_handler(event,some):
    try:
        # Read from DB and store each entry to [url, max_price, lowest_price, lowest_price_date, SNS_ARN]
        entries=read_dynamodb()

        # For each entry in DB
        # Crawl the current price 
        # compare the current_price with lowest_price.
        # update entry in DB
        for item in entries:
            try:
                url=item['url']
                lowest_price=item['lowest_price']
                SNS_ARN=item['SNS_ARN']
                current_price,title=price_crawl(url)
                if current_price is None or title is None:
                    logger.error(f"Failed to catch elements on the webpage {url}.")
                    continue
                if float(current_price)<float(item['lowest_price']):
                    sub=f"Price Drop alert!"
                    msg=f"Price drop on {title}: Now is {current_price}. The last lowest price was {lowest_price}. Check now {url}."
                    publish_sns(SNS_ARN,sub,msg)
                    logger.info(f'Publishing msg for {title}')
                    update_dynamodb_lowest_price(url,current_price)
                else:
                    logger.info(f"No lower price found for {title}")
            except (WebScrapingError, DynamoDBError, SNSError) as e:
                logger.error(f"Error processing item {item['url']}: {str(e)}")
                continue
        logger.info("Scan has finished.")
        return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Price check completed successfully'})
        }
    
    except Exception as e:
        logger.error(f"Unexpected error in lambda_handler: {str(e)}")
        return {
        'statusCode': 500,
        'body': json.dumps({'error': 'Internal server error'})
        }