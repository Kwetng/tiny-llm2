output "openai_endpoint" {
  description = "Private Azure OpenAI endpoint for the gateway (AZURE_OPENAI_ENDPOINT)"
  value       = azurerm_cognitive_account.openai.endpoint
}

output "search_endpoint" {
  value = "https://${azurerm_search_service.rag.name}.search.windows.net"
}

output "gateway_identity_client_id" {
  description = "Managed identity the gateway uses - no secrets in code"
  value       = azurerm_user_assigned_identity.gateway.client_id
}

output "audit_container" {
  value = "${azurerm_storage_account.audit.name}/${azurerm_storage_container.audit.name}"
}
