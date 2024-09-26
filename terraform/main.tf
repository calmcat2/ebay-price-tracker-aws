module "dynamodb" {
  source  = "terraform-aws-modules/dynamodb-table/aws"
  version = "~> 4.0"

  name           = var.table_name
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

