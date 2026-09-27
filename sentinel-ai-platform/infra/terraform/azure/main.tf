# Sentinel AI Platform - Azure landing zone for the AI gateway (UK South).
# Private by default: no public endpoints on any AI or data service, Entra ID auth only,
# customer-managed keys, diagnostics to Log Analytics, audit logs on immutable storage.

terraform {
  required_version = ">= 1.7"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
  }
}

provider "azurerm" {
  features {
    key_vault { purge_soft_delete_on_destroy = false }
  }
}

data "azurerm_client_config" "current" {}

locals {
  name = "${var.prefix}-${var.environment}"
  tags = merge(var.tags, { environment = var.environment, workload = "sentinel-ai-gateway", data_class = "confidential" })
}

resource "azurerm_resource_group" "ai" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}

# ---------------------------------------------------------------- monitoring
resource "azurerm_log_analytics_workspace" "ai" {
  name                = "log-${local.name}"
  location            = azurerm_resource_group.ai.location
  resource_group_name = azurerm_resource_group.ai.name
  sku                 = "PerGB2018"
  retention_in_days   = 365
  tags                = local.tags
}

# ---------------------------------------------------------------- network
resource "azurerm_virtual_network" "ai" {
  name                = "vnet-${local.name}"
  location            = azurerm_resource_group.ai.location
  resource_group_name = azurerm_resource_group.ai.name
  address_space       = [var.vnet_cidr]
  tags                = local.tags
}

resource "azurerm_subnet" "private_endpoints" {
  name                              = "snet-private-endpoints"
  resource_group_name               = azurerm_resource_group.ai.name
  virtual_network_name              = azurerm_virtual_network.ai.name
  address_prefixes                  = [cidrsubnet(var.vnet_cidr, 4, 0)]
  private_endpoint_network_policies = "Enabled"
}

resource "azurerm_network_security_group" "private_endpoints" {
  name                = "nsg-${local.name}-pe"
  location            = azurerm_resource_group.ai.location
  resource_group_name = azurerm_resource_group.ai.name
  tags                = local.tags

  security_rule {
    name                       = "allow-https-from-vnet"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "VirtualNetwork"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "private_endpoints" {
  subnet_id                 = azurerm_subnet.private_endpoints.id
  network_security_group_id = azurerm_network_security_group.private_endpoints.id
}

resource "azurerm_subnet" "apps" {
  name                 = "snet-gateway-apps"
  resource_group_name  = azurerm_resource_group.ai.name
  virtual_network_name = azurerm_virtual_network.ai.name
  address_prefixes     = [cidrsubnet(var.vnet_cidr, 4, 1)]
}

resource "azurerm_network_security_group" "apps" {
  name                = "nsg-${local.name}-apps"
  location            = azurerm_resource_group.ai.location
  resource_group_name = azurerm_resource_group.ai.name
  tags                = local.tags

  security_rule {
    name                       = "allow-https-from-corporate"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = var.corporate_cidr
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "apps" {
  subnet_id                 = azurerm_subnet.apps.id
  network_security_group_id = azurerm_network_security_group.apps.id
}

resource "azurerm_private_dns_zone" "zones" {
  for_each            = toset(["privatelink.openai.azure.com", "privatelink.search.windows.net", "privatelink.vaultcore.azure.net", "privatelink.blob.core.windows.net"])
  name                = each.value
  resource_group_name = azurerm_resource_group.ai.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "zones" {
  for_each              = azurerm_private_dns_zone.zones
  name                  = "link-${replace(each.key, ".", "-")}"
  resource_group_name   = azurerm_resource_group.ai.name
  private_dns_zone_name = each.value.name
  virtual_network_id    = azurerm_virtual_network.ai.id
}

# ---------------------------------------------------------------- keys
resource "azurerm_key_vault" "ai" {
  name                          = substr(replace("kv-${local.name}", "-", ""), 0, 24)
  location                      = azurerm_resource_group.ai.location
  resource_group_name           = azurerm_resource_group.ai.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "premium"
  purge_protection_enabled      = true
  soft_delete_retention_days    = 90
  enable_rbac_authorization     = true
  public_network_access_enabled = false
  tags                          = local.tags

  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
  }
}

resource "azurerm_key_vault_key" "cmk" {
  name            = "cmk-ai-data"
  key_vault_id    = azurerm_key_vault.ai.id
  key_type        = "RSA-HSM"
  key_size        = 3072
  key_opts        = ["wrapKey", "unwrapKey"]
  expiration_date = var.cmk_expiry

  rotation_policy {
    expire_after         = "P2Y"
    notify_before_expiry = "P30D"
    automatic { time_before_expiry = "P60D" }
  }
}

resource "azurerm_user_assigned_identity" "gateway" {
  name                = "id-${local.name}-gateway"
  location            = azurerm_resource_group.ai.location
  resource_group_name = azurerm_resource_group.ai.name
  tags                = local.tags
}

# ---------------------------------------------------------------- Azure OpenAI (Foundry)
resource "azurerm_cognitive_account" "openai" {
  name                          = "oai-${local.name}"
  location                      = azurerm_resource_group.ai.location
  resource_group_name           = azurerm_resource_group.ai.name
  kind                          = "OpenAI"
  sku_name                      = "S0"
  custom_subdomain_name         = "oai-${local.name}"
  public_network_access_enabled      = false
  local_auth_enabled                 = false # Entra ID tokens only - no API keys
  outbound_network_access_restricted = true  # data loss prevention: the service cannot call out
  fqdns                              = ["${azurerm_key_vault.ai.name}.vault.azure.net"] # only destination allowed: its CMK vault
  tags                               = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.gateway.id]
  }

  network_acls {
    default_action = "Deny"
  }
}

resource "azurerm_cognitive_account_customer_managed_key" "openai" {
  cognitive_account_id = azurerm_cognitive_account.openai.id
  key_vault_key_id     = azurerm_key_vault_key.cmk.id
  identity_client_id   = azurerm_user_assigned_identity.gateway.client_id
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = var.chat_deployment_name
  cognitive_account_id = azurerm_cognitive_account.openai.id
  model {
    format  = "OpenAI"
    name    = var.chat_model_name
    version = var.chat_model_version # pinned: a version change is a model change (GR-002 §3.1)
  }
  sku {
    name     = "Standard"
    capacity = var.chat_capacity_k_tpm
  }
  version_upgrade_option = "NoAutoUpgrade"
}

resource "azurerm_private_endpoint" "openai" {
  name                = "pe-${local.name}-openai"
  location            = azurerm_resource_group.ai.location
  resource_group_name = azurerm_resource_group.ai.name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = local.tags
  private_service_connection {
    name                           = "psc-openai"
    private_connection_resource_id = azurerm_cognitive_account.openai.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }
  private_dns_zone_group {
    name                 = "openai"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["privatelink.openai.azure.com"].id]
  }
}

# ---------------------------------------------------------------- Azure AI Search (hybrid retrieval)
resource "azurerm_search_service" "rag" {
  name                          = "srch-${local.name}"
  location                      = azurerm_resource_group.ai.location
  resource_group_name           = azurerm_resource_group.ai.name
  sku                           = "standard"
  replica_count                 = 3 # 3 replicas give the read/write (index update) SLA
  partition_count               = 1
  public_network_access_enabled = false
  local_authentication_enabled  = false
  semantic_search_sku           = "standard"
  customer_managed_key_enforcement_enabled = true
  tags                          = local.tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_private_endpoint" "search" {
  name                = "pe-${local.name}-search"
  location            = azurerm_resource_group.ai.location
  resource_group_name = azurerm_resource_group.ai.name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = local.tags
  private_service_connection {
    name                           = "psc-search"
    private_connection_resource_id = azurerm_search_service.rag.id
    subresource_names              = ["searchService"]
    is_manual_connection           = false
  }
  private_dns_zone_group {
    name                 = "search"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["privatelink.search.windows.net"].id]
  }
}

# ---------------------------------------------------------------- immutable audit storage
resource "azurerm_storage_account" "audit" {
  #checkov:skip=CKV_AZURE_33:Queue service is not used by this account; blob access is logged via diag-audit-blob
  name                            = substr(replace("staudit${local.name}", "-", ""), 0, 24)
  location                        = azurerm_resource_group.ai.location
  resource_group_name             = azurerm_resource_group.ai.name
  account_tier                    = "Standard"
  account_replication_type        = "GZRS"
  min_tls_version                 = "TLS1_2"
  public_network_access_enabled   = false
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
  infrastructure_encryption_enabled = true
  tags                            = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.gateway.id]
  }

  customer_managed_key {
    key_vault_key_id          = azurerm_key_vault_key.cmk.versionless_id
    user_assigned_identity_id = azurerm_user_assigned_identity.gateway.id
  }

  blob_properties {
    versioning_enabled = true
    delete_retention_policy { days = 365 }
    container_delete_retention_policy { days = 365 }
  }

  immutability_policy {
    allow_protected_append_writes = true
    state                         = "Unlocked" # lock after the first successful audit export review
    period_since_creation_in_days = var.audit_retention_days
  }

  sas_policy {
    expiration_period = "00.01:00:00"
  }
}

resource "azurerm_storage_container" "audit" {
  #checkov:skip=CKV2_AZURE_21:Blob read/write/delete logging is configured by azurerm_monitor_diagnostic_setting.audit_blob (Checkov only recognises the legacy storage analytics setting)
  name                  = "ai-audit"
  storage_account_id    = azurerm_storage_account.audit.id
  container_access_type = "private"
}

resource "azurerm_private_endpoint" "audit" {
  name                = "pe-${local.name}-audit"
  location            = azurerm_resource_group.ai.location
  resource_group_name = azurerm_resource_group.ai.name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = local.tags
  private_service_connection {
    name                           = "psc-audit"
    private_connection_resource_id = azurerm_storage_account.audit.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }
  private_dns_zone_group {
    name                 = "blob"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["privatelink.blob.core.windows.net"].id]
  }
}

resource "azurerm_private_endpoint" "keyvault" {
  name                = "pe-${local.name}-kv"
  location            = azurerm_resource_group.ai.location
  resource_group_name = azurerm_resource_group.ai.name
  subnet_id           = azurerm_subnet.private_endpoints.id
  tags                = local.tags
  private_service_connection {
    name                           = "psc-kv"
    private_connection_resource_id = azurerm_key_vault.ai.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }
  private_dns_zone_group {
    name                 = "kv"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["privatelink.vaultcore.azure.net"].id]
  }
}

resource "azurerm_monitor_diagnostic_setting" "audit_blob" {
  name                       = "diag-audit-blob"
  target_resource_id         = "${azurerm_storage_account.audit.id}/blobServices/default"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.ai.id
  enabled_log { category = "StorageRead" }
  enabled_log { category = "StorageWrite" }
  enabled_log { category = "StorageDelete" }
  enabled_metric { category = "Transaction" }
}

# ---------------------------------------------------------------- least-privilege access for the gateway
resource "azurerm_role_assignment" "gateway_openai" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.gateway.principal_id
}

resource "azurerm_role_assignment" "gateway_search" {
  scope                = azurerm_search_service.rag.id
  role_definition_name = "Search Index Data Reader"
  principal_id         = azurerm_user_assigned_identity.gateway.principal_id
}

resource "azurerm_role_assignment" "gateway_audit" {
  scope                = azurerm_storage_container.audit.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.gateway.principal_id
}

resource "azurerm_role_assignment" "cmk_access" {
  scope                = azurerm_key_vault.ai.id
  role_definition_name = "Key Vault Crypto Service Encryption User"
  principal_id         = azurerm_user_assigned_identity.gateway.principal_id
}

# ---------------------------------------------------------------- diagnostics
resource "azurerm_monitor_diagnostic_setting" "openai" {
  name                       = "diag-openai"
  target_resource_id         = azurerm_cognitive_account.openai.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.ai.id
  enabled_log { category_group = "allLogs" }
  enabled_metric { category = "AllMetrics" }
}

resource "azurerm_monitor_diagnostic_setting" "keyvault" {
  name                       = "diag-keyvault"
  target_resource_id         = azurerm_key_vault.ai.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.ai.id
  enabled_log { category_group = "audit" }
  enabled_metric { category = "AllMetrics" }
}
