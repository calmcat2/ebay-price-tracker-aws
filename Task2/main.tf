#1. Create a lambda function that scans the DynamoDB table 
module "lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "~> 7.9"

  function_name = "price_tracker_v1_schedule"
  handler       = "handler.lambda_handler"  
  runtime       = "python3.11"
  create_package = true

  source_path = "lambda_src/"
  layers=[var.lambda_layer_arn]

  timeout=30

  #created for test purpose, will be removed before production phase.
  create_lambda_function_url =true

  environment_variables = {
    DB = var.dynamodb_table_name
  }

  attach_policy_json = true
  policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:*",
          "logs:CreateLogGroup", 
          "logs:CreateLogStream", 
          "logs:PutLogEvents",
          "cloudwatch:DeleteAlarms",
          "cloudwatch:DescribeAlarmHistory",
          "cloudwatch:DescribeAlarms",
          "cloudwatch:DescribeAlarmsForMetric",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:ListMetrics",
          "cloudwatch:PutMetricAlarm",
          "cloudwatch:GetMetricData",
          "iam:GetRole",
          "iam:ListRoles",
          "kms:DescribeKey",
          "kms:ListAliases",
          "sns:CreateTopic",
          "sns:DeleteTopic",
          "sns:ListSubscriptions",
          "sns:ListSubscriptionsByTopic",
          "sns:ListTopics",
          "sns:Subscribe",
          "sns:Unsubscribe",
          "sns:SetTopicAttributes",
          "sns:Publish",
          "tag:GetResources"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = "cloudwatch:GetInsightRuleReport"
        Resource = "arn:aws:cloudwatch:*:*:insight-rule/DynamoDBContributorInsights*"
      }
    ]
  })

}
#2. Create a evenbridge that runs the lambda function periodically
resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.lambda_function_name
  principal     = "events.amazonaws.com"
  source_arn    = module.eventbridge.eventbridge_rule_arns["crons"]
}

module "eventbridge" {
  source = "terraform-aws-modules/eventbridge/aws"

  create_bus = false

  rules = {
    crons = {
      description         = "Trigger for a Lambda"
      schedule_expression = "rate(30 minutes)"
    }
  }

  targets = {
    crons = [
      {
        name  = "price_tracker_v1_schedule"
        arn   = module.lambda.lambda_function_arn
        input = jsonencode({"job": "cron-by-rate"})
      }
    ]
  }
}