terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }

  # State holds database endpoints and secret ARNs, not secret values — the
  # passwords are RDS-managed or written straight into Secrets Manager by hand.
  # Still worth a remote backend before a second person applies this: fill in
  # and uncomment.
  # backend "s3" {
  #   bucket       = "noharm-tfstate"
  #   key          = "prod/terraform.tfstate"
  #   region       = "us-east-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
