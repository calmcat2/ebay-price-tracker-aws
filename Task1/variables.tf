variable "aws_region" {
  description = "The AWS region to deploy resources in."
  default     = "us-east-1"
}

variable "dynamodb_table_name" {
  description = "The name of the DynamoDB table"
  default= "price_tracker_v1"
}

variable "lambda_layer"{
  default = "arn:aws:lambda:us-east-1:637423641675:layer:web_layer1:3"
}
variable "allowed_origins"{
  default=["https://app1.maxinehe.top"]
}

