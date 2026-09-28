CloudMart – E-Commerce Backend Platform

1. Project Overview

CloudMart is a cloud-based e-commerce backend platform designed to manage products, inventory, customer orders, authentication, notifications, reporting, and operational monitoring.

The application is built using AWS managed services and follows an Infrastructure as Code approach using AWS CloudFormation. The infrastructure is deployed through GitHub Actions using GitHub OIDC authentication.

Main Capabilities

Product management

Inventory management

Customer and administrator authentication

Order creation and order retrieval

Order cancellation

Inventory updates based on orders

Event-driven order processing

Low-stock notifications

Order confirmation, failure, and cancellation notifications

Daily report generation

EC2-based administration dashboard

CloudWatch monitoring and alarms

SNS-based operational notifications

Automated CI/CD deployment using GitHub Actions and CloudFormation

2. High-Level Architecture

CloudMart uses a VPC-based AWS architecture with public and private components.

Application Flow

                         ┌──────────────────┐
                         │      Client      │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │   API Gateway    │
                         └────────┬─────────┘
                                  │
                         ┌────────▼─────────┐
                         │ Lambda Authorizer│
                         └────────┬─────────┘
                                  │
                     ┌────────────┴────────────┐
                     │                         │
                     ▼                         ▼
           ┌─────────────────┐        ┌─────────────────┐
           │ Product Lambda  │        │  Order Lambda   │
           └────────┬────────┘        └────────┬────────┘
                    │                          │
                    └────────────┬─────────────┘
                                 ▼
                         ┌─────────────────┐
                         │   RDS MySQL     │
                         └─────────────────┘

Event-Driven Flow

Order Lambda
     │
     ▼
EventBridge Event Bus
     │
     ├──────────────► Order Notification ──► SNS ──► Email
     │
     └──────────────► Inventory Alert Lambda
                                      │
                                      ▼
                                     SNS
                                      │
                                      ▼
                                     Email

Reporting Flow

EventBridge Scheduled Rule
          │
          ▼
Report Generator Lambda
          │
          ├──────────► RDS MySQL
          │
          ▼
       CSV Report
          │
          ▼
       S3 Reports
          │
          ▼
      EC2 Dashboard

Monitoring Flow

AWS Resources
      │
      ▼
CloudWatch Metrics
      │
      ├────────► CloudWatch Dashboard
      │
      └────────► CloudWatch Alarms
                       │
                       ▼
                      SNS
                       │
                       ▼
                     Email

3. AWS Services Used

AWS Service

Purpose

Amazon VPC

Provides isolated network infrastructure

Amazon EC2

Hosts the Flask administration dashboard

Amazon RDS for MySQL

Stores application data

AWS Lambda

Implements application, authentication, inventory, reporting, and schema functionality

Amazon API Gateway

Exposes application APIs

Amazon EventBridge

Provides event-driven integration and scheduled execution

Amazon SNS

Sends notifications and alarm emails

Amazon S3

Stores Lambda artifacts, reports, and dashboard files

Amazon CloudWatch

Provides monitoring, metrics, dashboards, and alarms

AWS Systems Manager Parameter Store

Stores application configuration and database parameters

AWS IAM

Controls permissions and access

AWS CloudFormation

Provisions and manages infrastructure

GitHub Actions

Provides CI/CD automation

GitHub OIDC

Allows GitHub Actions to authenticate with AWS without long-lived AWS access keys

4. VPC and Networking

CloudMart uses a VPC with CIDR:

10.0.0.0/16

Network Layout

CloudMart VPC
10.0.0.0/16
│
├── Public Subnet
│   └── EC2 Flask Dashboard
│
├── Private Subnet
│   └── Lambda Functions
│
└── RDS Support Private Subnet
    └── RDS MySQL

Main Network Addresses

VPC:              10.0.0.0/16
Public Subnet:    10.0.1.0/24
Private Subnet:   10.0.2.0/24
RDS Subnet:       10.0.3.0/24

The EC2 dashboard is placed in the public subnet, while the application Lambda functions and RDS database are kept in private networking.

Security Groups control communication between the application components.

The RDS database is not directly exposed to the public internet.

5. Database

CloudMart uses Amazon RDS for MySQL as its relational database.

The database contains the following main tables:

USERS
PRODUCTS
INVENTORY
ORDERS
ORDER_ITEMS

USERS

Stores customer and administrator information.

Important fields include:

user_id
name
email
role
token_hash
created_at
updated_at

PRODUCTS

Stores product catalog information.

Important fields include:

product_id
name
description
price
category
is_deleted
created_at
updated_at

INVENTORY

Stores stock information for products.

Important fields include:

inventory_id
product_id
stock_count
low_stock_threshold
updated_at

Each product has a corresponding inventory record.

ORDERS

Stores customer order information.

Important fields include:

order_id
customer_id
total_amount
status
failure_reason
created_at
updated_at

ORDER_ITEMS

Stores the products included in each order.

Important fields include:

order_item_id
order_id
product_id
quantity
unit_price
subtotal

Database Relationships

USERS
  │
  │ 1
  │
  └──────────< ORDERS
                  │
                  │ 1
                  │
                  └──────────< ORDER_ITEMS >────────── PRODUCTS
                                                        │
                                                        │ 1
                                                        │
                                                        └──── INVENTORY

Foreign key relationships maintain referential integrity between related records.

6. Lambda Functions

CloudMart uses multiple Lambda functions for different responsibilities.

Product Lambda

Responsible for product operations:

Get all products

Get a product by ID

Create a product

Update a product

Delete a product

Product write operations are protected using the custom Lambda authorizer.

Order Lambda

Responsible for order operations:

Create orders

Retrieve orders

Retrieve customer-specific orders

Cancel orders

Order cancellation is implemented using PATCH so that the order record is retained rather than deleted.

The order process also updates inventory and publishes relevant events.

Inventory Alert Lambda

Receives inventory-related events from EventBridge and publishes low-stock notifications through SNS.

Authorizer Lambda

Authenticates requests using the application's authentication data stored in the database and determines whether the request should be allowed.

Report Generator Lambda

Runs on the scheduled EventBridge rule and:

Retrieves required data from RDS.

Generates the daily report.

Creates a CSV file.

Uploads the report to the Reports S3 bucket.

Publishes the report generation metric.

7. API

API Gateway provides HTTP endpoints for the application.

Main Resources

/products
/products/{id}

/orders
/orders/{id}

Product API

Product retrieval operations are available through GET endpoints.

Product creation, update, and deletion operations use authentication through the custom Lambda authorizer.

Order API

Orders support:

Creating an order

Getting orders

Getting customer-specific orders

Cancelling an order

Order cancellation uses PATCH rather than deleting the order so that the order history is retained.

8. Authentication and Authorization

CloudMart uses a custom Lambda authorizer.

The high-level request flow is:

Client
   │
   ▼
API Gateway
   │
   ▼
Lambda Authorizer
   │
   ├── Authentication successful
   │          │
   │          ▼
   │     Application Lambda
   │
   └── Authentication failed
              │
              ▼
            Denied

The application distinguishes between user and administrator roles.

Administrative dashboard access is also authenticated before dashboard functionality is provided.

9. Event-Driven Architecture

CloudMart uses Amazon EventBridge for event-driven integration.

The application publishes events for important order and inventory operations.

Examples include:

Order confirmed

Order failed

Order cancelled

Low-stock events

Report generation events

EventBridge rules process these events and route them to the appropriate targets.

For notification events, SNS is used to deliver email notifications.

10. Notifications

Amazon SNS is used for application and operational notifications.

Order Confirmation

A successful order generates an order confirmation notification.

Order Failure

A failed order generates a notification containing information such as the order ID, customer ID, status, total amount, and failure reason.

Order Cancellation

A cancelled order generates a cancellation notification.

Low Stock

When inventory reaches the configured low-stock condition, an inventory alert event is processed and an SNS notification is sent.

CloudWatch Alarms

CloudWatch alarms also send notifications through SNS when configured thresholds are breached.

11. Reporting

CloudMart generates a daily report using an EventBridge scheduled rule.

The report schedule is:

03:00 UTC
08:30 IST

The flow is:

EventBridge Schedule
        ↓
Report Generator Lambda
        ↓
RDS MySQL
        ↓
CSV Report
        ↓
S3 Reports Bucket

Reports are stored using the reports prefix:

reports/

The administration dashboard retrieves available reports from the S3 Reports bucket.

12. Administration Dashboard

The CloudMart dashboard is hosted on Amazon EC2.

The dashboard uses:

Flask
Gunicorn
Nginx
Amazon RDS
Amazon S3

Request Flow

Browser
   ↓
Nginx
   ↓
Gunicorn
   ↓
Flask
   ├── RDS MySQL
   └── S3 Reports

Nginx acts as the reverse proxy, Gunicorn runs the Flask application, and Flask handles dashboard requests and database/report operations.

The dashboard provides operational information such as:

Total Orders

Confirmed Orders

Failed Orders

Active Products

Users

Order Items

Total Revenue

Inventory

It also provides access to application tables and generated reports.

13. Monitoring

CloudMart uses Amazon CloudWatch for application and infrastructure monitoring.

Lambda Metrics

The monitoring dashboard includes:

Invocations

Errors

Duration

Throttles

Concurrent Executions

The monitored Lambda functions include:

Product Lambda

Order Lambda

Inventory Alert Lambda

Authorizer Lambda

Report Generator Lambda

API Gateway Metrics

The dashboard monitors:

API Gateway Count

API Gateway 4XX Errors

API Gateway 5XX Errors

RDS Metrics

The dashboard monitors:

CPU Utilization

Database Connections

Free Storage Space

Custom Application Metrics

CloudMart also publishes application-specific metrics for events such as:

Orders Created

Orders Failed

Orders Cancelled

Inventory Alerts

Reports Generated

These metrics provide application-level visibility in addition to standard AWS service metrics.

14. CloudWatch Alarms

CloudWatch alarms are configured for important operational conditions.

Examples include:

Order failures

Order cancellations

Low-stock/inventory alerts

Report generator errors

Lambda error rate

API Gateway errors

RDS CPU utilization

The notification flow is:

CloudWatch Alarm
       ↓
SNS Topic
       ↓
Email Notification

This allows operational issues to be detected without continuously checking the CloudWatch dashboard.

15. CI/CD Pipeline

CloudMart uses GitHub Actions for deployment automation.

The high-level flow is:

Developer
    ↓
GitHub Repository
    ↓
GitHub Actions
    ↓
GitHub OIDC
    ↓
AWS IAM Deployment Role
    ↓
AWS CloudFormation
    ↓
AWS Infrastructure

GitHub Actions authenticates with AWS using OIDC instead of storing long-lived AWS access keys.

GitHub Secrets

The workflow uses the following GitHub repository secrets:

AWS_ROLE_ARN
CLOUDMART_DB_PASSWORD
CLOUDMART_ORDER_EMAIL
CLOUDMART_LOW_STOCK_EMAIL
CLOUDMART_MONITORING_EMAIL

Secret Purposes

AWS_ROLE_ARN
IAM role assumed by GitHub Actions.

CLOUDMART_DB_PASSWORD
Database master password used during RDS deployment.

CLOUDMART_ORDER_EMAIL
Email address used for order notifications.

CLOUDMART_LOW_STOCK_EMAIL
Email address used for low-stock notifications.

CLOUDMART_MONITORING_EMAIL
Email address used for CloudWatch monitoring notifications.

Actual secret values must never be committed to the repository or documented in source code.

The database password is written to AWS Systems Manager Parameter Store as a SecureString before the Data stack is deployed.

16. AWS Systems Manager Parameter Store

CloudMart uses AWS Systems Manager Parameter Store for application configuration and database connection information.

The environment-specific parameter paths are:

/cloudmart/<environment>/db/password
/cloudmart/<environment>/db/host
/cloudmart/<environment>/db/port
/cloudmart/<environment>/db/name
/cloudmart/<environment>/db/username

/cloudmart/<environment>/notifications/order-email
/cloudmart/<environment>/notifications/low-stock-email

/cloudmart/<environment>/monitoring/email

For the current dev environment:

/cloudmart/dev/db/password
/cloudmart/dev/db/host
/cloudmart/dev/db/port
/cloudmart/dev/db/name
/cloudmart/dev/db/username

/cloudmart/dev/notifications/order-email
/cloudmart/dev/notifications/low-stock-email

/cloudmart/dev/monitoring/email

Parameter Creation Flow

The database password is created by the GitHub Actions workflow before the Data stack is deployed because the RDS resource requires the password during database creation.

The Data stack creates the following parameters after RDS is provisioned:

/cloudmart/<environment>/db/host
/cloudmart/<environment>/db/port
/cloudmart/<environment>/db/name
/cloudmart/<environment>/db/username

The Data stack also creates:

/cloudmart/<environment>/notifications/order-email
/cloudmart/<environment>/notifications/low-stock-email

The Monitoring stack creates:

/cloudmart/<environment>/monitoring/email

The API stack consumes the existing notification parameters.

The Report Generator Lambda and other application components consume the database configuration parameters from SSM as required.

17. Infrastructure as Code

CloudMart infrastructure is managed using AWS CloudFormation.

Stack Deployment Order

Network
   ↓
SSM
   ↓
Data
   ↓
Security
   ↓
Artifacts
   ↓
Schema
   ↓
Auth
   ↓
API
   ↓
Reporting
   ↓
Monitoring
   ↓
Final Verification

The stack dependencies are deployed in this order so that required networking, parameters, database resources, IAM permissions, Lambda artifacts, authentication, APIs, reporting, and monitoring are available when dependent resources are created.

The only manual infrastructure setup required for CI/CD is the one-time bootstrap of the GitHub OIDC provider and GitHub Actions deployment role.

18. Environment Configuration

CloudMart is designed to support environment-based deployment.

The current environment is:

Environment: dev
AWS Region: ap-south-1

Examples of environment-specific stacks include:

cloudmart-dev-network
cloudmart-dev-data
cloudmart-dev-security
cloudmart-dev-schema
cloudmart-dev-auth
cloudmart-dev-api
cloudmart-dev-reporting
cloudmart-dev-monitoring

This approach helps keep resources separated between environments.

19. Security

Security is implemented using multiple AWS mechanisms.

IAM

IAM roles are used to provide AWS permissions to Lambda functions, EC2, GitHub Actions, and other components.

Permissions are scoped according to the resources required by each component.

Security Groups

Security Groups control network access between EC2, Lambda, and RDS components.

The RDS database is not directly exposed to the public internet.

Systems Manager Parameter Store

Database configuration values are stored in SSM Parameter Store.

The database password is stored as a SecureString.

Notification configuration values are also stored as environment-specific SSM parameters.

GitHub OIDC

GitHub Actions uses OIDC to assume the AWS deployment role without requiring long-lived AWS access keys.

Session Security

The Flask dashboard session secret is generated on the EC2 instance during deployment and stored in a protected local file rather than being hard-coded in the application source code.

20. S3 Storage

S3 is used for several purposes in CloudMart.

Lambda Artifacts

Lambda deployment packages are stored in an S3 artifact bucket.

Examples include packages for:

Product Lambda

Order Lambda

Inventory Alert Lambda

Authorizer Lambda

Report Generator Lambda

Schema Runner Lambda

Reports

Generated daily reports are stored in the Reports S3 bucket.

Dashboard Files

Dashboard application files such as:

app.py
index.html

are stored in the dashboard S3 prefix and downloaded to the EC2 instance during dashboard setup.

21. Deployment and Verification

After deployment, the following areas should be verified.

CloudFormation

Verify that all CloudMart stacks reach:

CREATE_COMPLETE

or

UPDATE_COMPLETE

RDS

Verify that the database is available and that the required tables exist:

users
products
inventory
orders
order_items

Lambda

Verify that the expected Lambda functions are deployed.

API Gateway

Verify the product and order API resources and their configured authorization.

EventBridge

Verify the event bus, rules, and targets.

SNS

Verify notification topics and subscriptions.

S3

Verify Lambda artifacts, dashboard files, and generated reports.

EC2 Dashboard

Verify that the dashboard is accessible and that the Flask application, Gunicorn service, and Nginx reverse proxy are running.

CloudWatch

Verify the dashboard, metrics, and alarms.

A detailed step-by-step deployment procedure is maintained separately in the CloudMart Deployment Runbook.

22. Functional Verification

The following application operations should be verified after deployment.

Products

GET     /products
GET     /products/{id}
POST    /products
PUT     /products/{id}
DELETE  /products/{id}

Orders

POST    /orders
GET     /orders
PATCH   /orders/{id}

Order creation should update inventory and publish the appropriate event.

Order cancellation should restore the relevant inventory and publish the cancellation event.

Notifications

Verify:

Order confirmation notification

Order failure notification

Order cancellation notification

Low-stock notification

CloudWatch alarm notification

23. Technology Stack

Backend

Python
Flask
Gunicorn
MySQL

Cloud

AWS Lambda
Amazon API Gateway
Amazon RDS
Amazon EC2
Amazon S3
Amazon EventBridge
Amazon SNS
Amazon CloudWatch
AWS Systems Manager Parameter Store
AWS IAM
Amazon VPC
AWS CloudFormation

CI/CD

GitHub
GitHub Actions
GitHub OIDC

24. Key Design Decisions

Why CloudFormation?

CloudFormation provides Infrastructure as Code so that infrastructure can be consistently created, updated, and managed.

Why GitHub OIDC?

OIDC avoids the need to store long-lived AWS access keys in GitHub.

Why RDS MySQL?

A relational database fits the structured relationships between users, products, inventory, orders, and order items.

Why EventBridge?

EventBridge provides event-driven integration between application components and supports scheduled execution for reporting.

Why SNS?

SNS provides a simple mechanism for delivering application and operational notifications through email.

Why CloudWatch?

CloudWatch provides centralized monitoring, metrics, dashboards, and alarms for AWS resources and CloudMart application behavior.

Why EC2 for the Dashboard?

The Flask dashboard is hosted on EC2 and uses Nginx and Gunicorn to provide a web-accessible administration interface.

25. Project Summary

CloudMart is an AWS-based e-commerce backend platform that combines:

Serverless application components

Relational data storage

Event-driven processing

Automated notifications

Scheduled reporting

EC2-based administration

Centralized monitoring

Infrastructure as Code

Automated CI/CD

The project demonstrates how multiple AWS services can be integrated into a complete cloud application while maintaining controlled networking, authentication, monitoring, and deployment automation.

26. Documentation

Additional project documentation includes:

Architecture Diagram

Data Model Documentation

Deployment Runbook

CloudFormation stack documentation

API and application documentation

These documents provide detailed information beyond the overview provided in this README.

27. Environment

Project:        CloudMart
Environment:    dev
AWS Region:     ap-south-1
Database:       Amazon RDS for MySQL
Deployment:     GitHub Actions
Infrastructure: AWS CloudFormation