CloudMart – E-Commerce Backend Platform

1. Project Overview

CloudMart is a cloud-based e-commerce backend platform built using AWS managed services. It provides product and inventory management, user authentication, order processing, event-driven processing, notifications, scheduled reporting, an EC2-based Flask administration dashboard, and centralized monitoring.

The project uses AWS CloudFormation for Infrastructure as Code and GitHub Actions with GitHub OIDC for automated deployment.

Main Capabilities

Product management

Inventory management

User and administrator authentication

Order creation and retrieval

Order cancellation

Inventory updates during order processing

Event-driven order processing

Failed-order persistence

Low-stock notifications

Order confirmation, failure, and cancellation notifications

Daily report generation

S3-based report storage

EC2 Flask administration dashboard

CloudWatch monitoring and alarms

SNS-based operational notifications

Automated CI/CD deployment

Environment-based AWS resource configuration

2. Architecture Overview

The final CloudMart architecture consists of a CI/CD layer, API and authentication layer, application Lambda functions, RDS MySQL, EventBridge, SNS, reporting, monitoring, and an EC2 administration dashboard.

The architecture is organized around the following major flows:

Developer
    |
    v
GitHub
    |
    v
GitHub Actions
    |
    v
CloudFormation
    |
    v
AWS Infrastructure

The application request flow is:

Client
  |
  v
API Gateway
  |
  v
Authorizer Lambda
  |
  +-----------------------------+
  |                             |
  v                             v
Valid User                 Invalid User
  |                             |
  v                             v
Allow Request              HTTP 401
  |                        Unauthorized
  |
  +----------------------+----------------------+
  |                                             |
  v                                             v
Product / Inventory Lambda                Order Lambda
  |                                             |
  +----------------------+----------------------+
                         |
                         v
                    RDS MySQL

Order processing produces order events:

Order Lambda
     |
     v
Order Confirmed / Failed / Cancelled
     |
     v
CloudMart EventBridge Event Bus

EventBridge then routes events to the required processing components:

CloudMart EventBridge Event Bus
        |
        +----> Order Failed Handler
        |          |
        |          v
        |       RDS MySQL
        |       Failed-order persistence
        |
        +----> Inventory Alert Lambda
        |          |
        |          v
        |         SNS
        |
        +----> EventBridge Scheduled Rule
                   |
                   v
             Report Generator Lambda
                   |
                   v
                S3 Reports
                   |
                   v
             EC2 Flask Dashboard

Operational monitoring follows:

CloudWatch Alarms
       |
       v
      SNS
       |
       v
Operations Team

3. CI/CD Architecture

CloudMart uses GitHub Actions and AWS CloudFormation for deployment.

Developer
    |
    v
GitHub Repository
    |
    v
GitHub Actions
    |
    v
GitHub OIDC
    |
    v
AWS IAM Deployment Role
    |
    v
CloudFormation
    |
    v
AWS Infrastructure

GitHub Actions authenticates to AWS using OIDC, avoiding the need for long-lived AWS access keys.

The deployment workflow validates CloudFormation templates and deploys the CloudMart infrastructure through the required CloudFormation stacks.

The project uses environment-based naming, with the current environment being dev.

4. AWS Services Used

AWS Service

Purpose

Amazon VPC

Provides isolated network infrastructure

Amazon API Gateway

Exposes CloudMart HTTP APIs

AWS Lambda

Runs application, authentication, inventory-alert, reporting, and database functions

Amazon RDS for MySQL

Stores users/authentication, products, inventory, and orders

Amazon EventBridge

Provides event-driven processing and scheduled report execution

Amazon SNS

Sends application and operational notifications

Amazon S3

Stores Lambda artifacts, reports, and dashboard files

Amazon EC2

Hosts the Flask administration dashboard

Amazon CloudWatch

Provides logs, metrics, dashboards, and alarms

AWS Systems Manager Parameter Store

Stores application and database configuration

AWS IAM

Controls AWS permissions

AWS CloudFormation

Provides Infrastructure as Code

GitHub Actions

Automates deployment

GitHub OIDC

Provides secure GitHub-to-AWS authentication

5. VPC and Networking

CloudMart uses a VPC-based architecture.

The main VPC CIDR is:

10.0.0.0/16

Network Layout

                         VPC
                    10.0.0.0/16
                         |
              +----------+----------+
              |                     |
           Public                 Private
              |                     |
       EC2 Dashboard        +--------+--------+
                             |        |        |
                            RDS   Order Lambda  |
                                   Inventory    |
                                   Alert Lambda |
                                   Product      |
                                   Lambda       |
                                   Auth Lambda  |

Main Subnets

Public Subnet:        10.0.1.0/24
Private Subnet:       10.0.2.0/24
RDS Support Subnet:   10.0.3.0/24

The architecture places the EC2 Flask Dashboard in the public subnet.

The private side contains:

RDS MySQL

Order Lambda

Inventory Alert Lambda

Product/Inventory Lambda

Authorizer Lambda

The RDS database is not directly exposed to the public internet.

VPC Endpoints

The private application components use VPC endpoints for required AWS service connectivity.

Configured endpoints include:

Amazon S3 Gateway Endpoint

SSM Interface Endpoint

CloudWatch Logs Interface Endpoint

CloudWatch monitoring interface connectivity

EventBridge Interface Endpoint

This design provides private connectivity to AWS services without requiring a NAT Gateway for the project architecture.

Security Groups

Security groups control communication between the application components.

The RDS security group permits MySQL traffic only from the required application security group rather than from the public internet.

6. Database

CloudMart uses Amazon RDS for MySQL.

The architecture shows RDS MySQL as the central relational data store for authentication and application data.

The main tables are:

USERS
PRODUCTS
INVENTORY
ORDERS
ORDER_ITEMS

USERS

Stores user and authentication information.

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

Stores products included in each order.

Important fields include:

order_item_id

order_id

product_id

quantity

unit_price

subtotal

Database Relationships

USERS
  |
  +------< ORDERS
              |
              +------< ORDER_ITEMS >------ PRODUCTS
                                            |
                                            +------ INVENTORY

Foreign-key relationships maintain relationships between the database entities.

7. API and Authentication Flow

The CloudMart architecture uses:

Client
  |
  v
API Gateway
  |
  v
Authorizer Lambda
  |
  v
RDS MySQL
Users/Auth

The Authorizer Lambda validates the requesting user against the authentication information stored in RDS.

Authentication Decision

                 Authorizer Lambda
                        |
                 Validate User
                        |
             +----------+----------+
             |                     |
             v                     v
        Valid User            Invalid User
             |                     |
             v                     v
       Allow Request           HTTP 401
                               Unauthorized

Only an authenticated request proceeds to the application Lambda functions.

Token Validation

The application stores token information securely using a hash.

The authorization process is:

Bearer Token
     |
     v
SHA-256 Hash
     |
     v
Compare with token_hash
stored in RDS
     |
     v
Identify User + Role
     |
     v
Allow / Deny

The raw token is not stored as plain text.

Role-Based Authorization

CloudMart distinguishes between application users and administrators.

The authenticated role is used when determining whether an API request should be allowed.

Administrative product operations are protected from unauthorized users.

8. Application Lambda Functions

CloudMart uses multiple Lambda functions for separate responsibilities.

Product / Inventory Lambda

The architecture represents product and inventory operations through the Product/Inventory Lambda component.

Responsibilities include:

Product retrieval

Product creation

Product update

Product deletion

Inventory-related application operations

Protected write operations require successful authorization.

Order Lambda

The Order Lambda is responsible for:

Creating orders

Retrieving orders

Retrieving customer-specific orders

Retrieving an order by ID

Cancelling orders

Updating inventory during order processing

Publishing order events

The order process produces:

Order Confirmed
Order Failed
Order Cancelled

These events are sent to the CloudMart EventBridge Event Bus.

Inventory Alert Lambda

The Inventory Alert Lambda receives inventory-related events from EventBridge.

It is responsible for processing low-stock conditions and sending the appropriate notification through SNS.

Authorizer Lambda

The Authorizer Lambda:

Receives the authorization information from API Gateway.

Extracts the bearer token.

Hashes the token.

Checks the authentication information in RDS.

Determines the user's role.

Allows or denies the request.

Invalid authentication results in:

HTTP 401 Unauthorized

Report Generator Lambda

The Report Generator Lambda runs from the EventBridge scheduled rule.

It:

Retrieves required database configuration.

Connects to RDS MySQL.

Retrieves report data.

Generates a CSV report.

Uploads the report to S3.

Publishes the report-generation metric.

Schema Runner Lambda

The Schema Runner Lambda is used during deployment to apply the CloudMart database schema.

9. API Endpoints

The main API resources are:

/products
/products/{id}

/orders
/orders/{id}

Product Operations

GET     /products
GET     /products/{id}
POST    /products
PUT     /products/{id}
DELETE  /products/{id}

Order Operations

POST    /orders
GET     /orders
GET     /orders/{id}
PATCH   /orders/{id}

Order cancellation uses PATCH so that the order record remains available for historical purposes instead of physically deleting the record.

10. Order Processing

The Order Lambda performs the order workflow.

A simplified successful order flow is:

Client
  |
  v
API Gateway
  |
  v
Authorizer Lambda
  |
  v
Order Lambda
  |
  +----> Validate / process order
  |
  +----> Update inventory
  |
  +----> Persist order in RDS
  |
  v
Order Confirmed Event
  |
  v
EventBridge

If order processing fails:

Order Lambda
     |
     v
Order Failed Event
     |
     v
EventBridge
     |
     v
Order Failed Handler
     |
     v
RDS MySQL
Failed-order failure persisted

For cancellation:

Order Lambda
     |
     v
Update order status
     |
     v
Restore relevant inventory
     |
     v
Order Cancelled Event
     |
     v
EventBridge

11. Event-Driven Architecture

CloudMart uses Amazon EventBridge as the central event bus.

The architecture specifically contains:

CloudMart EventBridge Event Bus

Important order events include:

Order Confirmed

Order Failed

Order Cancelled

The EventBridge bus routes events to the required targets.

Order Failed Handler

The Order Failed Handler receives the failed-order event and persists the relevant failed-order/failure information in RDS MySQL.

Order Failed
     |
     v
EventBridge
     |
     v
Order Failed Handler
     |
     v
RDS MySQL
Failed-order failure persisted

Inventory Alert

Inventory-related events are routed to:

EventBridge
     |
     v
Inventory Alert Lambda
     |
     v
SNS

This separates event generation from notification processing.

12. Notifications

Amazon SNS is used for notification delivery.

The architecture routes notification processing to SNS, which then delivers messages to the configured email recipients.

Order Notifications

The application supports notifications for:

Order confirmation

Order failure

Order cancellation

Low-Stock Notifications

When an inventory event meets the low-stock condition:

Inventory Event
      |
      v
EventBridge
      |
      v
Inventory Alert Lambda
      |
      v
SNS
      |
      v
Email

Operational Alerts

CloudWatch alarms use SNS for operational notifications:

CloudWatch Alarm
      |
      v
SNS
      |
      v
Operations Team

13. Reporting

CloudMart generates a daily report using an EventBridge scheduled rule.

Reporting Flow

EventBridge Scheduled Rule
          |
          v
Report Generator Lambda
          |
          v
RDS MySQL
          |
          v
CSV Report
          |
          v
S3 Reports
          |
          v
EC2 Flask Dashboard

The report generator retrieves required information from RDS and creates a CSV report.

Reports are stored under:

reports/

Report Schedule

The configured schedule is:

03:00 UTC
08:30 IST

The EC2 dashboard provides access to generated reports.

14. EC2 Flask Administration Dashboard

The administration dashboard is hosted on Amazon EC2.

The dashboard uses:

Flask

Gunicorn

Nginx

RDS MySQL

S3

SSM Parameter Store

Dashboard Request Flow

Browser
   |
   v
Nginx
   |
   v
Gunicorn
   |
   v
Flask
   |
   +------> RDS MySQL
   |
   +------> S3 Reports
   |
   +------> SSM Parameter Store

Nginx

Nginx acts as the reverse proxy.

Gunicorn

Gunicorn runs the Flask application.

Flask

Flask handles:

Dashboard routes

Administrator authentication

Session management

Database queries

Report listing

Report download operations

Dashboard Information

The dashboard provides operational information such as:

Total Orders

Confirmed Orders

Failed Orders

Active Products

Users

Order Items

Total Revenue

Inventory

Generated Reports

15. Dashboard Authentication

The EC2 dashboard requires administrator authentication before protected dashboard functionality is available.

The Flask application uses a session mechanism to maintain the authenticated state.

The dashboard session:

Uses a generated/configured secret stored on the EC2 instance.

Does not hard-code the secret in app.py.

Uses protected session-cookie settings.

Uses a 60-minute inactivity timeout.

The session secret is stored on the EC2 instance at:

/etc/cloudmart-dashboard-secret

16. Monitoring

CloudMart uses Amazon CloudWatch for monitoring.

Monitoring covers both AWS service metrics and CloudMart application metrics.

Lambda Monitoring

Standard Lambda metrics include:

Invocations

Errors

Duration

Throttles

Concurrent Executions

The monitored application functions include:

Product Lambda

Order Lambda

Inventory Alert Lambda

Authorizer Lambda

Report Generator Lambda

API Gateway Monitoring

The monitoring dashboard includes:

API request count

API Gateway 4XX errors

API Gateway 5XX errors

RDS Monitoring

The monitoring dashboard includes:

CPU utilization

Database connections

Free storage space

17. Custom CloudWatch Metrics

CloudMart publishes application-specific metrics to CloudWatch.

Important metrics include:

OrdersFailed
OrdersCancelled
InventoryAlerts
ReportsGenerated
LowStockEvents

These metrics provide business/application-level visibility in addition to standard AWS service metrics.

Example

When an order is cancelled:

Order Cancellation
       |
       v
Order Lambda
       |
       +----> OrdersCancelled metric
       |
       +----> OrderCancelled event
                    |
                    v
               EventBridge

Similarly, report generation publishes the report-generation metric.

18. CloudWatch Alarms

CloudWatch alarms are configured for important operational conditions.

Examples include:

Order failures

Order cancellations

Inventory/low-stock alerts

Report Generator Lambda errors

Lambda error conditions

API Gateway errors

RDS CPU utilization

Alarm Flow

CloudWatch Metric
       |
       v
CloudWatch Alarm
       |
       v
SNS
       |
       v
Operations Team

The purpose of the alarms is to notify the operations team when configured thresholds are breached.

19. AWS Systems Manager Parameter Store

CloudMart uses SSM Parameter Store for environment-specific configuration.

The main parameter paths are:

/cloudmart/<environment>/db/password
/cloudmart/<environment>/db/host
/cloudmart/<environment>/db/port
/cloudmart/<environment>/db/name
/cloudmart/<environment>/db/username

/cloudmart/<environment>/notifications/order-email
/cloudmart/<environment>/notifications/low-stock-email

/cloudmart/<environment>/monitoring/email

For the current development environment:

/cloudmart/dev/db/password
/cloudmart/dev/db/host
/cloudmart/dev/db/port
/cloudmart/dev/db/name
/cloudmart/dev/db/username

/cloudmart/dev/notifications/order-email
/cloudmart/dev/notifications/low-stock-email

/cloudmart/dev/monitoring/email

Parameter Creation

The database password is created before the Data stack is deployed because RDS requires the password during database creation.

The Data stack then creates the database connection parameters after RDS is provisioned.

The notification parameters are also created for the application components.

The monitoring stack creates the monitoring email parameter.

The application Lambdas retrieve required configuration from SSM at runtime.

20. Infrastructure as Code

CloudMart infrastructure is managed using AWS CloudFormation.

The main CloudFormation stacks are:

Network
SSM
Data
Security
Artifacts
Schema
Auth
API
Reporting
Monitoring

Deployment Order

Network
   |
   v
SSM
   |
   v
Data
   |
   v
Security
   |
   v
Artifacts
   |
   v
Schema
   |
   v
Auth
   |
   v
API
   |
   v
Reporting
   |
   v
Monitoring
   |
   v
Final Verification

The stack order ensures that dependent resources are available before the components that consume them are deployed.

21. CloudFormation Stack Responsibilities

Network Stack

Responsible for the networking foundation:

VPC

Public subnet

Private subnet

RDS support subnet

Route tables

Security groups

VPC endpoints

SSM Stack

Responsible for environment-specific configuration parameters that are required during deployment.

Data Stack

Responsible for:

RDS MySQL

S3 resources

Database-related parameters

Notification parameters

Security Stack

Responsible for IAM roles and permissions required by the application resources.

Artifacts Stack

Provides the S3 location used for Lambda deployment artifacts.

Schema Stack

Deploys and executes the database schema runner.

Auth Stack

Creates the Authorizer Lambda and its required IAM permissions.

API Stack

Creates the main application API resources, including:

API Gateway

Product/Inventory Lambda

Order Lambda

Inventory Alert Lambda

EventBridge event bus

EventBridge rules

SNS notification resources

Reporting Stack

Creates the reporting resources, including:

Report Generator Lambda

EventBridge scheduled rule

S3 report integration

EC2 dashboard resources

Monitoring Stack

Creates:

CloudWatch dashboard

CloudWatch alarms

Monitoring SNS topic

Monitoring email subscription

Monitoring-related configuration

22. Security

CloudMart uses multiple security controls.

IAM

IAM roles provide permissions to:

Lambda functions

EC2 dashboard

GitHub Actions

Other AWS resources

Permissions are scoped according to component responsibilities.

Security Groups

Security groups restrict network communication between application components.

RDS is not directly exposed to the public internet.

Parameter Store

Configuration values are stored in SSM Parameter Store.

The database password is stored as a SecureString.

GitHub OIDC

GitHub Actions authenticates to AWS through OIDC rather than long-lived AWS access keys.

Authentication Token Security

The application stores token hashes rather than plain-text authentication tokens.

The Authorizer Lambda hashes the supplied token before checking the corresponding token_hash in RDS.

Dashboard Session Security

The Flask dashboard session secret is generated/configured on the EC2 instance and stored separately from the application source code.

23. S3 Storage

S3 is used for several CloudMart resources.

Lambda Artifacts

Lambda deployment packages are stored in an S3 artifacts bucket.

The packages include functions such as:

Product Lambda
Order Lambda
Inventory Alert Lambda
Authorizer Lambda
Report Generator Lambda
Schema Runner Lambda

Reports

Generated reports are stored under:

reports/

Dashboard Files

Dashboard files are stored in the dashboard S3 location and are used during EC2 dashboard setup.

Important files include:

app.py
index.html

24. Environment Configuration

The current deployment uses:

Environment: dev
AWS Region: ap-south-1

Environment-specific naming is used for CloudFormation stacks and SSM parameters.

Examples:

cloudmart-dev-network
cloudmart-dev-data
cloudmart-dev-security
cloudmart-dev-schema
cloudmart-dev-auth
cloudmart-dev-api
cloudmart-dev-reporting
cloudmart-dev-monitoring

This approach keeps resources and configuration separated by environment.

25. Deployment Verification

After deployment, the following components should be verified.

CloudFormation

Verify that stacks reach:

CREATE_COMPLETE

or:

UPDATE_COMPLETE

RDS

Verify:

RDS is available.

Database connectivity works.

Required tables exist.

Required tables:

users
products
inventory
orders
order_items

Lambda

Verify the expected Lambda functions are deployed.

API Gateway

Verify:

API exists.

Product resources exist.

Order resources exist.

Authorizer is configured.

Methods are deployed.

EventBridge

Verify:

CloudMart event bus exists.

Order event rules exist.

Inventory alert rule exists.

Scheduled reporting rule exists.

SNS

Verify:

Application notification topics exist.

Monitoring topic exists.

Required email subscriptions are configured.

S3

Verify:

Lambda artifacts exist.

Dashboard files exist.

Reports are generated under the reports prefix.

EC2 Dashboard

Verify:

EC2 is running.

Flask files are present.

Gunicorn is running.

Nginx is running.

Dashboard login works.

Dashboard data loads correctly.

Reports are accessible.

CloudWatch

Verify:

Dashboard exists.

Standard AWS metrics are visible.

Custom CloudMart metrics are being published.

Required alarms exist.

Alarm actions point to SNS.

26. Functional Verification

Product APIs

GET     /products
GET     /products/{id}
POST    /products
PUT     /products/{id}
DELETE  /products/{id}

Verify:

Product retrieval works.

Authorized product creation works.

Authorized product update works.

Authorized product deletion works.

Unauthorized requests are rejected.

Order APIs

POST    /orders
GET     /orders
GET     /orders/{id}
PATCH   /orders/{id}

Verify:

Order creation works.

Inventory is updated.

Successful orders produce the confirmation event.

Failed orders are persisted correctly.

Failed-order processing reaches the Order Failed Handler.

Order cancellation updates the order status.

Relevant inventory is restored after cancellation.

Order cancellation produces the cancellation event.

Notifications

Verify:

Order confirmation notification

Order failure notification

Order cancellation notification

Low-stock notification

CloudWatch alarm notification

Reporting

Verify:

EventBridge scheduled rule is enabled.

Report Generator Lambda runs.

CSV report is created.

Report is stored in S3.

Report appears in the EC2 dashboard.

27. Repository Structure

CloudMart-Capstone/
|
+-- .github/
|   +-- workflows/
|       +-- deploy.yaml
|
+-- cloudformation/
|   +-- Network-stack.yaml
|   +-- Data-stack.yaml
|   +-- Security-stack.yaml
|   +-- schema-stack.yaml
|   +-- Auth-stack.yaml
|   +-- api-stack.yaml
|   +-- Reporting-stack.yaml
|   +-- monitoring-stack.yaml
|
+-- lambda/
|   +-- product/
|   |   +-- lambda_function.py
|   |
|   +-- order/
|   |   +-- lambda_function.py
|   |
|   +-- inventory-alert/
|   |   +-- lambda_function.py
|   |
|   +-- authorizer/
|   |   +-- lambda_function.py
|   |
|   +-- report/
|   |   +-- lambda_function.py
|   |
|   +-- schema-runner/
|       +-- lambda_function.py
|
+-- dashboard/
|   +-- app.py
|   +-- index.html
|   +-- requirements.txt
|
+-- docs/
|
+-- README.md

28. Technology Stack

Application

Python

Flask

Gunicorn

MySQL

PyMySQL

Boto3

AWS

Amazon VPC

Amazon API Gateway

AWS Lambda

Amazon RDS for MySQL

Amazon EC2

Amazon S3

Amazon EventBridge

Amazon SNS

Amazon CloudWatch

AWS Systems Manager Parameter Store

AWS IAM

AWS CloudFormation

CI/CD

GitHub

GitHub Actions

GitHub OIDC

Web Server

Nginx

Gunicorn

Flask

29. Key Design Decisions

Why CloudFormation?

CloudFormation provides Infrastructure as Code.

It allows CloudMart infrastructure to be deployed consistently and divided into logical stacks.

Why GitHub OIDC?

GitHub OIDC allows GitHub Actions to authenticate with AWS without storing long-lived AWS access keys.

This improves deployment credential security.

Why RDS MySQL?

CloudMart has structured relationships between:

Users

Products

Inventory

Orders

Order Items

A relational database is suitable for these relationships and supports transactional application operations.

Why EventBridge?

EventBridge provides the central event bus shown in the architecture.

It separates event production from downstream processing and also provides the scheduled trigger used by the reporting workflow.

Why SNS?

SNS provides notification delivery for application events and operational CloudWatch alarms.

Why CloudWatch?

CloudWatch provides:

AWS service metrics

Application metrics

Dashboards

Alarms

Monitoring visibility

Why EC2 for the Dashboard?

The administration dashboard is a Flask web application hosted on EC2.

Nginx acts as the reverse proxy and Gunicorn runs the Flask application.

This provides a dedicated interface for administrators and the operations team.

Why VPC Endpoints?

Private application components need connectivity to AWS services such as S3, SSM, CloudWatch Logs, monitoring APIs, and EventBridge.

VPC endpoints provide private access to these services without requiring a NAT Gateway for the project design.

Why PATCH for Order Cancellation?

Order cancellation changes the state of an existing order instead of deleting the order.

This preserves the order history and allows cancelled orders to remain available for reporting and auditing.

30. Complete End-to-End Architecture Flow

The complete CloudMart flow is:

                         DEVELOPER
                             |
                             v
                           GITHUB
                             |
                             v
                       GITHUB ACTIONS
                             |
                             v
                       CLOUDFORMATION
                             |
                             v
                     AWS INFRASTRUCTURE
                             |
                             v
                           CLIENT
                             |
                             v
                       API GATEWAY
                             |
                             v
                     AUTHORIZER LAMBDA
                             |
                     Validate User
                             |
                 +-----------+-----------+
                 |                       |
                 v                       v
            Valid User             Invalid User
                 |                       |
                 v                       v
           Allow Request              HTTP 401
                 |
          +------+------+
          |             |
          v             v
 Product/Inventory   Order Lambda
     Lambda               |
          |               |
          +-------+-------+
                  |
                  v
              RDS MySQL
                  |
                  v
       Order Confirmed / Failed /
             Cancelled
                  |
                  v
       EventBridge CloudMart
             Event Bus
                  |
       +----------+-----------+
       |          |           |
       v          v           v
  Scheduled    Order Failed  Inventory
     Rule       Handler       Alert
       |            |           |
       v            v           v
 Report          RDS          SNS
 Generator     Failed           |
 Lambda         Order           v
       |        Data           Email
       v
 S3 Reports
       |
       v
EC2 Flask Dashboard
       |
       v
Operations Team


CloudWatch
    |
    v
CloudWatch Alarms
    |
    v
SNS
    |
    v
Operations Team

31. Project Summary

CloudMart demonstrates a complete AWS-based e-commerce backend architecture combining:

API Gateway

Custom Lambda authentication

Product and inventory processing

Order processing

Amazon RDS MySQL

EventBridge event-driven architecture

Failed-order persistence

SNS notifications

Scheduled reporting

S3 report storage

EC2 Flask administration dashboard

CloudWatch monitoring

CloudWatch alarms

VPC-based networking

IAM security

SSM Parameter Store

AWS CloudFormation

GitHub Actions

GitHub OIDC

The architecture separates application processing, asynchronous event handling, reporting, administration, and monitoring while keeping sensitive application and database resources inside private networking.

32. Environment

Project:          CloudMart
Environment:      dev
AWS Region:       ap-south-1
Database:         Amazon RDS for MySQL
Deployment:       GitHub Actions
Infrastructure:   AWS CloudFormation
Dashboard:        EC2 + Flask + Gunicorn + Nginx

33. Documentation

Additional project documentation can include:

Architecture documentation

Database/data model documentation

Deployment runbook

CloudFormation stack documentation

API documentation

Application documentation

These documents provide detailed implementation information beyond this README.

Final Architecture at a Glance

CI/CD
Developer
   |
GitHub
   |
GitHub Actions
   |
CloudFormation
   |
AWS Infrastructure


APPLICATION
Client
   |
API Gateway
   |
Authorizer Lambda
   |
   +---- Valid ----> Product/Inventory Lambda
   |                       |
   |                       |
   |                  RDS MySQL
   |
   +---- Valid ----> Order Lambda
                           |
                           v
                       RDS MySQL
                           |
                           v
                  EventBridge Event Bus
                     /      |       \
                    /       |        \
                   v        v         v
             Failed      Inventory  Scheduled
             Handler       Alert       Rule
                |           |           |
                v           v           v
               RDS         SNS       Report
                                      Lambda
                                         |
                                         v
                                      S3 Reports
                                         |
                                         v
                                    EC2 Dashboard


MONITORING
AWS/Application Metrics
          |
          v
      CloudWatch
          |
          v
        Alarms
          |
          v
         SNS
          |
          v
    Operations Team


NETWORK
VPC
 |
 +-- Public
 |     |
 |     +-- EC2 Dashboard
 |
 +-- Private
       |
       +-- RDS MySQL
       +-- Order Lambda
       +-- Inventory Alert Lambda
       +-- Product/Inventory Lambda
       +-- Authorizer Lambda