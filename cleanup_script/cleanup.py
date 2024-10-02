import boto3, subprocess,json
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
sns_client = boto3.client('sns')
table = dynamodb.Table('price_tracker_v1')

def read_dynamodb():
    items = []

    try:
        # Define the attributes you want to retrieve
        projection_expression = "SNS_ARN"
        
        # Scan the table with ProjectionExpression
        response = table.scan(
            ProjectionExpression=projection_expression,
        )
        items.extend(response['Items'])

        # If there are more items, keep scanning
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                ProjectionExpression=projection_expression,
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response['Items'])
        
        print(f"Successfully read {len(items)} items from the table.")
        sns_list=[]
        for item in items:
            sns_list.append(item['SNS_ARN'])
        print (f'List of SNS ARN in the table {sns_list}')
        return sns_list
    except ClientError as e:
        print(f"Error reading from DynamoDB table {table}: {e}")
        return None
def cleanup_sns(sns_list):
    result = subprocess.run(['aws', 'sns', 'list-topics'], capture_output=True, text=True)
    topics = json.loads(result.stdout)['Topics']
    print(f'\n List of all topics in SNS {topics}\n')
    for topic in topics:
        if topic['TopicArn'] not in sns_list:
            subprocess.run(['aws', 'sns', 'delete-topic', '--topic-arn', topic['TopicArn']])
            print(f"Deleted topic: {topic}")

def main():
    sns_list=read_dynamodb()
    if sns_list:
        cleanup_sns(sns_list)
    else:
        print("no sns found in the dynamodb.")
if __name__ == "__main__":
    main()
