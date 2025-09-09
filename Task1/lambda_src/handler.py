import json
import boto3
import os, time
import logging
import requests
import re
from bs4 import BeautifulSoup as bs
import datetime
from botocore.exceptions import ClientError
from typing import Dict, Tuple, Any, Optional

# Initialize services
dynamodb = boto3.resource("dynamodb")
sns_client = boto3.client("sns")
table = dynamodb.Table(os.environ["DB"])
PRIMARY_KEY = "url"

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class ValidationError(Exception):
    """Raised when input validation fails."""

    pass


class WebScrapingError(Exception):
    """Raised when web scraping operations fail."""

    pass


class DynamoDBError(Exception):
    """Raised when DynamoDB operations fail."""

    pass


class SNSError(Exception):
    """Raised when SNS operations fail."""

    pass


def process_subscription(url: str, email: str) -> None:
    """
    Update dynamodb and sns after a price crawl.
    """
    try:
        current_price, title = price_crawl(url)
        if not current_price or not title:
            raise WebScrapingError(f"Failed to retrieve item information for {url}.")

        response = table.get_item(Key={PRIMARY_KEY: url})

        if "Item" in response:
            logging.info("Found an entry in DB.")
            item = response["Item"]
            subscribers = item.get("subscribers", [])

            if email not in subscribers:
                update_dynamodb_subscribers(url, email)
                update_sns_subscribers(item["SNS_ARN"], email)
                logging.info(f"Adding {email} to the subscribers list")
            else:
                update_sns_subscribers(item["SNS_ARN"], email)
                logging.info(
                    "The tracking item and subscribers are already in the DB. Resent a subscription confirmation email to {email}."
                )
        else:
            logging.info(f"No entry found for {url}. Creating a new one.")
            sns_arn = create_sns(title, email)
            logging.info(f"Created a new SNS with arn: {sns_arn}")
            add_dynamodb_item(title, current_price, email, sns_arn, url)
            logging.info("Added a new entry in DB.")

    except ClientError as e:
        # Wrap the original exception and raise a domain-specific one.
        raise DynamoDBError("Failed to query or update DynamoDB") from e


def add_dynamodb_item(
    title: str, current_price: str, email: str, sns_arn: str, url: str
) -> None:
    """
    Add a new entry in the dynamodb.
    """
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
            "SNS_ARN": sns_arn,
        }
        table.put_item(Item=item)
        logging.info(f"Added new entry in the DB for {url}")
    except ClientError as e:
        raise DynamoDBError("Failed to add entry to DynamoDB.") from e


def update_dynamodb_subscribers(url: str, email: str) -> None:
    """
    Update subscribers with new subscriber in a dynamodb entry.
    """
    try:
        table.update_item(
            Key={PRIMARY_KEY: url},
            UpdateExpression="SET subscribers = list_append(if_not_exists(subscribers, :empty_list), :new_email)",
            ExpressionAttributeValues={":empty_list": [], ":new_email": [email]},
            ReturnValues="UPDATED_NEW",
        )
        logging.info(f"Updated entry with new subscriber for {url}")
    except ClientError as e:
        raise DynamoDBError("Failed to update subscribers in DynamoDB") from e


def create_sns(title: str, subscriber: str) -> str:
    """
    Create a new sns topic and return the topic's arn
    """
    try:
        topic_name = re.sub(r"[^a-zA-Z0-9-_]", "_", title)[:256]
        response = sns_client.create_topic(Name=topic_name)
        topic_arn = response["TopicArn"]

        logging.info(f"Created SNS topic: {title}")
        logging.info(f"Topic ARN: {topic_arn}")

        sns_client.subscribe(TopicArn=topic_arn, Protocol="email", Endpoint=subscriber)

        logging.info(f"Subscribed {subscriber} to the topic {title}.")
        return topic_arn
    except ClientError as e:
        raise SNSError("Failed to create SNS topic or subscribe") from e


def update_sns_subscribers(sns_arn: str, email: str) -> None:
    """
    Add a subscriber to an sns arn.
    """
    try:
        sns_client.subscribe(TopicArn=sns_arn, Protocol="email", Endpoint=email)
        logging.info(f"Added subscriber {email} to SNS topic {sns_arn}")
    except ClientError as e:
        raise SNSError("Failed to update SNS subscribers") from e


def price_crawl(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Scrape the provided url for product Item name and current price.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            soup = bs(response.text, "html.parser")

            title_element = soup.find("span", class_="ux-textspans ux-textspans--BOLD")
            price_element = soup.find(
                "span",
                class_="ux-textspans",
                string=lambda text: text and text.strip().startswith("US $"),
            )
            logging.info(f"title: {title_element}  price: {price_element}")
            if title_element and price_element:
                title = title_element.text.strip()[:256]
                price = (
                    price_element.text.strip()
                    .replace("US $", "")
                    .replace(",", "")
                    .split("/")[0]
                )

                try:
                    float(price)
                    logging.info(
                        f"Successfully scraped - Title: "
                        f"{title[:50]}..., Price: ${price}"
                    )
                    return price, title
                except ValueError:
                    logging.warning(f"Invalid price format: {price}")
                    return None, None
            else:
                logging.error(
                    f"Attemp {attempt + 1} - Failed to catch elements on the webpage {url}."
                )
                if attempt < 2:
                    time.sleep(1)
                    continue
                return None, None
        except requests.RequestException as e:
            if attempt < 2:
                logging.warning(
                    f"Attemp {attempt + 1} - Failed to visit the webpage {url}. Retrying..."
                )
                time.sleep(1)
                continue
            raise WebScrapingError(f"Failed to scrape {url} after 3 attempts.") from e
    return None, None


def create_response(status_code: int, body: Dict[str, str]) -> Dict[str, Any]:
    """
    Create a http response.
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "https://app1.maxinehe.top",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "OPTIONS,POST",
        },
        "body": json.dumps(body),
    }


def validate_input(url: str, email: str) -> None:
    """
    Validate email format.
    """
    if not url:
        raise ValidationError("URL parameter is required")
    if not email:
        raise ValidationError("Email parameter is required")

    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(email_pattern, email):
        raise ValidationError(f"Invalid email address: {email}")

    url_pattern = r"^https://www\.ebay\.com/itm/\d+/?(\?.*)?$"
    if not re.match(url_pattern, url):
        raise ValidationError(f"Invalid eBay URL format: {url}")


def lambda_handler(event, context):
    """
    AWS Lambda handler as the main entrypoint.
    """
    try:
        logging.info(f"Event: {json.dumps(event)}")
        query_params = event.get("queryStringParameters", {}) or {}
        url = query_params.get("url")
        email = query_params.get("email")

        validate_input(url, email)

        logging.info(f"Processing request for URL: {url} and email: {email}")

        process_subscription(url, email)
        return create_response(200, {"message": "Signed up successfully!"})

    except ValidationError as e:
        logging.warning(f"Validation error: {str(e)}")
        return create_response(400, {"error": str(e)})
    except WebScrapingError as e:
        logging.exception(f"Web scraping error for {url}")
        return create_response(400, {"error": "Failed to retrieve item information"})
    except (DynamoDBError, SNSError) as e:
        logging.exception("An AWS service error occurred.")
        return create_response(500, {"error": str(e)})
    except Exception as e:
        logging.exception("An unexpected error occurred in the lambda handler.")
        return create_response(500, {"error": "Internal server error"})
