variable "aws_region" {
  description = "The AWS region to deploy resources in."
  default     = "us-east-1"
}

variable "dynamodb_table_name" {
  description = "The name of the DynamoDB table"
  default= "price_tracker_v1"
}
variable "lambda_layer_arn"{
    type=string
  #default="arn:aws:lambda:us-east-1:637423641675:layer:price_tracker_v1_layer:8"
}