variable "aws_region" {
  description = "The AWS region to deploy resources in."
  default     = "us-east-1"
}

variable "table_name" {
  description = "The name of the DynamoDB table"
  default= "price_tracker_v1"
}