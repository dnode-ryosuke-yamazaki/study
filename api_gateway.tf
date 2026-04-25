# =====================================================
# API Gateway REST API
# =====================================================
# HTTPリクエストを受け付けてLambda関数に振り分けるAPI Gateway
resource "aws_api_gateway_rest_api" "notes_api" {
  name           = "notes-api-${var.environment}"
  description    = "Notes API - OpenAPI仕様に準拠したRESTful API"
  
  tags = {
    Name        = "notes-api"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# =====================================================
# API Gateway リソース：/notes
# =====================================================
resource "aws_api_gateway_resource" "notes" {
  rest_api_id = aws_api_gateway_rest_api.notes_api.id
  parent_id   = aws_api_gateway_rest_api.notes_api.root_resource_id
  path_part   = "notes"
}

# =====================================================
# API Gateway リソース：/notes/{noteId}
# =====================================================
resource "aws_api_gateway_resource" "notes_item" {
  rest_api_id = aws_api_gateway_rest_api.notes_api.id
  parent_id   = aws_api_gateway_resource.notes.id
  path_part   = "{noteId}"
}

# =====================================================
# API Gateway メソッド：GET /notes
# =====================================================
resource "aws_api_gateway_method" "notes_list" {
  rest_api_id   = aws_api_gateway_rest_api.notes_api.id
  resource_id   = aws_api_gateway_resource.notes.id
  http_method   = "GET"
  authorization = "NONE"
  
  request_parameters = {
    "method.request.querystring.userId" = true
  }
}

# =====================================================
# API Gateway メソッド：POST /notes
# =====================================================
resource "aws_api_gateway_method" "notes_create" {
  rest_api_id   = aws_api_gateway_rest_api.notes_api.id
  resource_id   = aws_api_gateway_resource.notes.id
  http_method   = "POST"
  authorization = "NONE"
}

# =====================================================
# API Gateway メソッド：GET /notes/{noteId}
# =====================================================
resource "aws_api_gateway_method" "notes_get" {
  rest_api_id   = aws_api_gateway_rest_api.notes_api.id
  resource_id   = aws_api_gateway_resource.notes_item.id
  http_method   = "GET"
  authorization = "NONE"
  
  request_parameters = {
    "method.request.path.noteId" = true
  }
}

# =====================================================
# API Gateway メソッド：PUT /notes/{noteId}
# =====================================================
resource "aws_api_gateway_method" "notes_update" {
  rest_api_id   = aws_api_gateway_rest_api.notes_api.id
  resource_id   = aws_api_gateway_resource.notes_item.id
  http_method   = "PUT"
  authorization = "NONE"
  
  request_parameters = {
    "method.request.path.noteId" = true
  }
}

# =====================================================
# API Gateway メソッド：DELETE /notes/{noteId}
# =====================================================
resource "aws_api_gateway_method" "notes_delete" {
  rest_api_id   = aws_api_gateway_rest_api.notes_api.id
  resource_id   = aws_api_gateway_resource.notes_item.id
  http_method   = "DELETE"
  authorization = "NONE"
  
  request_parameters = {
    "method.request.path.noteId" = true
  }
}

# =====================================================
# API Gateway 統合：Lambda との連携
# =====================================================
resource "aws_api_gateway_integration" "notes_list_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.notes_api.id
  resource_id             = aws_api_gateway_resource.notes.id
  http_method             = aws_api_gateway_method.notes_list.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.hello_world.invoke_arn
}

resource "aws_api_gateway_integration" "notes_create_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.notes_api.id
  resource_id             = aws_api_gateway_resource.notes.id
  http_method             = aws_api_gateway_method.notes_create.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.hello_world.invoke_arn
}

resource "aws_api_gateway_integration" "notes_get_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.notes_api.id
  resource_id             = aws_api_gateway_resource.notes_item.id
  http_method             = aws_api_gateway_method.notes_get.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.hello_world.invoke_arn
}

resource "aws_api_gateway_integration" "notes_update_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.notes_api.id
  resource_id             = aws_api_gateway_resource.notes_item.id
  http_method             = aws_api_gateway_method.notes_update.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.hello_world.invoke_arn
}

resource "aws_api_gateway_integration" "notes_delete_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.notes_api.id
  resource_id             = aws_api_gateway_resource.notes_item.id
  http_method             = aws_api_gateway_method.notes_delete.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.hello_world.invoke_arn
}

# =====================================================
# API Gateway デプロイメント
# =====================================================
resource "aws_api_gateway_deployment" "notes" {
  depends_on = [
    aws_api_gateway_integration.notes_list_lambda,
    aws_api_gateway_integration.notes_create_lambda,
    aws_api_gateway_integration.notes_get_lambda,
    aws_api_gateway_integration.notes_update_lambda,
    aws_api_gateway_integration.notes_delete_lambda
  ]
  
  rest_api_id = aws_api_gateway_rest_api.notes_api.id
  
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.notes.id,
      aws_api_gateway_resource.notes_item.id,
      aws_api_gateway_method.notes_list.id,
      aws_api_gateway_method.notes_create.id,
      aws_api_gateway_method.notes_get.id,
      aws_api_gateway_method.notes_update.id,
      aws_api_gateway_method.notes_delete.id,
      aws_api_gateway_integration.notes_list_lambda.id,
      aws_api_gateway_integration.notes_create_lambda.id,
      aws_api_gateway_integration.notes_get_lambda.id,
      aws_api_gateway_integration.notes_update_lambda.id,
      aws_api_gateway_integration.notes_delete_lambda.id,
    ]))
  }
  
  lifecycle {
    create_before_destroy = true
  }
}

# =====================================================
# API Gateway ステージ
# =====================================================
resource "aws_api_gateway_stage" "notes" {
  deployment_id = aws_api_gateway_deployment.notes.id
  rest_api_id   = aws_api_gateway_rest_api.notes_api.id
  stage_name    = var.environment
  
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway_log_group_notes.arn
    format = jsonencode({
      requestId          = "$context.requestId"
      ip                 = "$context.identity.sourceIp"
      requestTime        = "$context.requestTime"
      httpMethod         = "$context.httpMethod"
      resourcePath       = "$context.resourcePath"
      status             = "$context.status"
      protocol           = "$context.protocol"
      responseLength     = "$context.responseLength"
      integrationLatency = "$context.integration.latency"
    })
  }
  
  tags = {
    Name        = "notes-api-stage"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}

# =====================================================
# CloudWatch Logs ロググループ：API Gateway
# =====================================================
resource "aws_cloudwatch_log_group" "api_gateway_log_group_notes" {
  name              = "/aws/apigateway/notes-api-${var.environment}"
  retention_in_days = 30
  
  tags = {
    Name        = "api-gateway-notes-log-group"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}
