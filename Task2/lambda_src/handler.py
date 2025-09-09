import json
import boto3
import os
import logging
import time
from botocore.exceptions import ClientError
from botocore.config import Config
from bs4 import BeautifulSoup as bs
import requests
import datetime
from typing import Tuple, Optional

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

retry_config = Config(retries={"max_attempts": 5, "mode": "standard"})

dynamodb = boto3.resource("dynamodb", config=retry_config)
sns_client = boto3.client("sns", config=retry_config)
table = dynamodb.Table(os.environ["DB"])



class WebScrapingError(Exception):
    """Raised when web scraping operations fail."""

    pass


class DynamoDBError(Exception):
    """Raised when DynamoDB operations fail."""

    pass


class SNSError(Exception):
    """Raised when SNS operations fail."""

    pass


def price_crawl(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Scrape price and title from eBay item page with retry logic.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }

    for attempt in range(3):  # MAX_RETRIES = 3
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = bs(response.text, "html.parser")
            logging.info(f"Loading webpage {url}...")

            title_element = soup.find("span", class_="ux-textspans ux-textspans--BOLD")
            price_element = soup.find(
                "span",
                class_="ux-textspans",
                string=lambda text: text and text.strip().startswith("US $"),
            )

            if title_element and price_element:
                title = title_element.text.strip()[:256]
                price_text = price_element.text.strip()
                price = price_text.replace("US $", "").replace(",", "").split("/")[0]

                # Validate price is numeric
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
                logging.warning(
                    f"Could not find price/title elements " f"on attempt {attempt + 1}"
                )
                if attempt < 2:
                    time.sleep(1)
                    continue
                return None, None

        except requests.RequestException as e:
            logging.warning(f"Request failed on attempt {attempt + 1}: {str(e)}")
            if attempt < 2:
                time.sleep(1)
                continue
            raise WebScrapingError(
                f"Failed to scrape {url} after 3 " f"attempts: {str(e)}"
            )

    return None, None


def read_dynamodb() -> Optional[list]:
    """
    Read dynamodb table.
    """
    items = []

    try:
        projection_expression = (
            "#u, max_price, lowest_price, lowest_price_date, SNS_ARN"
        )
        expression_attribute_names = {"#u": "url"}

        response = table.scan(
            ProjectionExpression=projection_expression,
            ExpressionAttributeNames=expression_attribute_names,
        )
        items.extend(response["Items"])

        # If there are more items, keep scanning
        while "LastEvaluatedKey" in response:
            response = table.scan(
                ProjectionExpression=projection_expression,
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response["Items"])

        logging.info(f"Successfully read {len(items)} items from the table.")
        return items

    except ClientError as e:
        logging.error(f"Error reading from DynamoDB table {table}: {e}")
        return None


def update_dynamodb_lowest_price(url: str, lowest_price: str) -> dict:
    """
    Update dynamodb entry with new lowest price and date.
    """
    lowest_price_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        response = table.update_item(
            Key={"url": url},
            UpdateExpression="SET lowest_price = :val1, lowest_price_date = :val2",
            ExpressionAttributeValues={
                ":val1": lowest_price,
                ":val2": lowest_price_date,
            },
            ReturnValues="UPDATED_NEW",
        )
        logging.info(f"Updated lowest price for {url}")
        return response["Attributes"]
    except ClientError as e:
        raise DynamoDBError(f"Error updating lowest price for {url}") from e


def publish_sns(sns_arn: str, subject: str, body: str) -> str:
    """
    Publish a message to an SNS topic.
    """
    try:
        response = sns_client.publish(TopicArn=sns_arn, Subject=subject, Message=body)

        logging.info(f"Message published to SNS topic {sns_arn}")
        return response["MessageId"]

    except ClientError as e:
        raise SNSError(f"Error publishing message to SNS topic {sns_arn}") from e


def lambda_handler(event, context):
    """
    AWS Lambda handler for scheduled price checking.
    """
    try:
        logging.info("Starting price check scan...")

        # Read from DB and get all tracked items
        entries = read_dynamodb()
        if not entries:
            logging.warning("No entries found in database")
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "No items to check"}),
            }

        logging.info(f"Found {len(entries)} items to check")
        processed_count = 0
        error_count = 0
        price_drop_count = 0

        # For each entry in DB
        # Crawl the current price
        # Compare the current_price with lowest_price
        # Update entry in DB if price dropped
        for item in entries:
            try:
                url = item["url"]
                lowest_price = item["lowest_price"]
                sns_arn = item["SNS_ARN"]

                current_price, title = price_crawl(url)
                if current_price is None or title is None:
                    logging.error(f"Failed to scrape webpage {url}")
                    error_count += 1
                    continue

                processed_count += 1

                if float(current_price) < float(item["lowest_price"]):
                    subject = "Price Drop Alert!"
                    message = (
                        f"Price drop on {title}: "
                        f"Now ${current_price}. "
                        f"Previous lowest was ${lowest_price}. "
                        f"Check now: {url}"
                    )

                    publish_sns(sns_arn, subject, message)
                    logging.info(f"Price drop notification sent for {title}")
                    update_dynamodb_lowest_price(url, current_price)
                    price_drop_count += 1
                else:
                    logging.info(
                        f"No price drop for {title[:30]}... " f"(${current_price})"
                    )

            except (WebScrapingError, DynamoDBError, SNSError) as e:
                logging.error(
                    f"Error processing item {item.get('url', 'unknown')}: " f"{str(e)}"
                )
                error_count += 1
                continue

        logging.info(
            f"Price check completed. Processed: {processed_count}, "
            f"Errors: {error_count}, Price drops: {price_drop_count}"
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Price check completed successfully",
                    "processed": processed_count,
                    "errors": error_count,
                    "price_drops": price_drop_count,
                }
            ),
        }

    except Exception as e:
        logging.exception("An unexpected error occurred in the lambda handler.")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
        }
