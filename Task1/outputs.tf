output "lamdba_arn" {
  value = module.lambda.lambda_function_arn
}

output "lambda_url"{
    value=module.lambda.lambda_function_url
}

output "CF_url"{
  value=module.cdn.cloudfront_distribution_domain_name
}

output "api_gateway_url" {
  description = "API Gateway URL"
  value       = module.api_gateway.api_endpoint
}
output "api_arn"{
 description="price_tracker_v1_api_arn"
 value=module.api_gateway.api_arn
}

output "lambda_layer"{
  value= module.lambda_layer.lambda_layer_arn
}