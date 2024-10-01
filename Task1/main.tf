#1. create dynamodb
module "dynamodb" {
  source  = "terraform-aws-modules/dynamodb-table/aws"
  version = "~> 4.0"

  name           = var.dynamodb_table_name
  hash_key       = "url"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1

  attributes = [
    {
      name = "url"
      type = "S"
    }
    
  ]
}

#2. create lambda function
module "lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "~> 7.9"

  function_name = "price_tracker_v1"
  handler       = "handler.lambda_handler"  
  runtime       = "python3.11"
  create_package = true

  source_path = "lambda_src/"
  layers=[module.lambda_layer.lambda_layer_arn]

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

module "lambda_layer" {
  source = "terraform-aws-modules/lambda/aws"

  create_layer = true

  layer_name          = "price_tracker_v1_layer"
  description         = "lambda layer created for price_tracker_v1"
  compatible_runtimes = ["python3.11"]

  source_path = "lambda_layer/"
}

#3. Create a API gateway with a POST call trigering the lambda function above
module "api_gateway" {
  source  = "terraform-aws-modules/apigateway-v2/aws"
  version = "~> 5.2"

  name          = "price-tracker-v1"
  description   = "API Gateway for Price Tracker Lambda"
  protocol_type = "HTTP"

  cors_configuration = {
    allow_headers = ["content-type", "x-amz-date", "authorization", "x-api-key", "x-amz-security-token", "x-amz-user-agent"]
    allow_methods = ["POST", "OPTIONS"]
    allow_origins = var.allowed_origins
    max_age       = 300
  }

# Disable domain name creation
  create_domain_name = false

  # Define the integration with your Lambda function
  routes = {
    "POST /" = {
      integration = {
        type   = "AWS_PROXY"
        uri    = module.lambda.lambda_function_arn
        credentials_arn = "${aws_iam_role.api_gateway_role.arn}"
        payload_format_version = "2.0"
        timeout_milliseconds   = 12000
      }
    }
  }  
}

# Grant necessary permissions
resource "aws_iam_role" "api_gateway_role" {
  name = "price_tracker_v1_api_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "apigateway.amazonaws.com"
        }
      }
    ]
  })

}
resource "aws_iam_role_policy" "api_gateway_policy" {
  name = "price_tracker_v1_api_gateway_policy"
  role = aws_iam_role.api_gateway_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          module.lambda.lambda_function_arn
        ]
      }
    ]
  })
}


resource "aws_lambda_permission" "api_gw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.lambda_function_name
  principal     = "apigateway.amazonaws.com"

  # The /*/* part allows invocation from any stage, method and resource path
  # within API Gateway.
  source_arn = "${module.api_gateway.api_execution_arn}/*/POST/*"

}

#4. Create a S3 bucket hosting files for our static website
module "s3_bucket" {
  source = "terraform-aws-modules/s3-bucket/aws"

  bucket = "price-tracker-v1-webpage"
  control_object_ownership = true
  object_ownership         = "ObjectWriter"

  cors_rule = [
    {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "POST"]
    allowed_origins = var.allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
    }
  ]

}

#upload necessary files for static website
resource "aws_s3_object" "objects" {
  for_each = fileset("s3_files", "**/*")
  
  bucket = module.s3_bucket.s3_bucket_id
  key    = each.value
  source = "s3_files/${each.value}"
  etag   = filemd5("s3_files/${each.value}")
  content_type = lookup({
    "html" = "text/html",
    "css"  = "text/css",
    "js"   = "application/javascript",
  }, split(".", each.value)[length(split(".", each.value)) - 1], "application/octet-stream")
}

#Need to modify the javascript file to use specified API url 
resource "aws_s3_object" "js_file" {
  bucket = module.s3_bucket.s3_bucket_id
  key    = "javascript.js"
  content = templatefile("s3_files/javascript.js.tpl", {
    baseUrl = module.api_gateway.api_endpoint
    })
  content_type = "application/javascript"
}

#5. Create cloudfront
module "acm_request_certificate" {
  source  = "terraform-aws-modules/acm/aws"
  version = "~> 4.0"

  domain_name = "app1.maxinehe.top"
  wait_for_validation = true
  validation_timeout="30m"
  validation_method = "DNS"
  create_route53_records  = false
  validate_certificate = false
}

module "cdn" {
  source  = "terraform-aws-modules/cloudfront/aws"
  version = "~> 3.0"

  comment             = "CloudFront for price tracker v1"
  enabled             = true
  is_ipv6_enabled     = true
  price_class         = "PriceClass_100"
  retain_on_delete    = false
  wait_for_deployment = false

  create_origin_access_control = true
  origin_access_control = {
    s3_oac = {
      description      = "OAC for price_tracker_v1 bucket"
      origin_type      = "s3"
      signing_behavior = "always"
      signing_protocol = "sigv4"
    }
  }

  origin = {
    s3_origin = {
      domain_name=module.s3_bucket.s3_bucket_bucket_domain_name
      origin_access_control = "s3_oac"
    }
  }
  aliases = ["app1.maxinehe.top"]
  default_root_object ="index.html"
  
  default_cache_behavior = {
    target_origin_id       = "s3_origin"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS"]
    cached_methods  = ["GET", "HEAD"]
    compress        = true
    query_string    = true
    headers = ["Origin"]
    response_headers_policy_id = aws_cloudfront_response_headers_policy.cors.id
  }
  viewer_certificate = {
    acm_certificate_arn = module.acm_request_certificate.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version  = "TLSv1.2_2021"
  }
  depends_on = [module.acm_request_certificate.cert]
}

resource "aws_cloudfront_response_headers_policy" "cors" {
name    = "cors-policy"
comment = "CORS policy"

cors_config {
    access_control_allow_credentials = false

    access_control_allow_headers {
    items = ["*"]
    }

    access_control_allow_methods {
    items = ["GET", "POST", "OPTIONS"]
    }

    access_control_allow_origins {
    items = var.allowed_origins
    }

    origin_override = false
    }
}


# Grant read permission to the CloudFront origin access control
resource "aws_s3_bucket_policy" "bucket_policy_cloudfront_access" {
  bucket = module.s3_bucket.s3_bucket_id

  policy = <<EOF
{
    "Version": "2008-10-17",
    "Id": "PolicyForCloudFrontPrivateContent",
    "Statement": [
        {
            "Sid": "AllowCloudFrontServicePrincipal",
            "Effect": "Allow",
            "Principal": {
                "Service": "cloudfront.amazonaws.com"
            },
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::${module.s3_bucket.s3_bucket_id}/*",
            "Condition": {
                "StringEquals": {
                    "AWS:SourceArn": "${module.cdn.cloudfront_distribution_arn}"
                }
            }
        }
    ]
}
EOF
}


