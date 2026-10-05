CloudMart – Deployment Runbook
Project: CloudMart – E-Commerce Backend Platform
Environment: <environment>
AWS Region: ap-south-1
Deployment Platform: GitHub Actions
Repository: https://github.com/likithareddy-05/CloudMart-Capstone
Infrastructure as Code: AWS CloudFormation
Database: Amazon RDS for MySQL
________________________________________
1. Purpose
This document provides the step-by-step procedure for deploying the CloudMart application and its AWS infrastructure.
The runbook covers:
•	Prerequisites 
•	CI/CD bootstrap 
•	Required GitHub secrets 
•	Deployment order 
•	CloudFormation stacks 
•	Database initialization 
•	Application deployment 
•	Dashboard deployment 
•	Monitoring and notification setup 
•	Post-deployment verification 
•	Troubleshooting 
•	Deployment completion checklist 
The objective is to ensure that CloudMart can be deployed consistently through GitHub Actions and AWS CloudFormation.
________________________________________



2. Deployment Architecture
CloudMart uses GitHub Actions for automated deployment.
Developer
    |
    v
GitHub Repository
    |
    v
GitHub Actions
    |
    | AWS OIDC Authentication
    v
AWS Deployment Role
    |
    v
CloudFormation
    |
    +------------------------------------+
    |                                    |
    v                                    v
AWS Infrastructure             Lambda Artifacts
                                         |
                                         v
                                        S3

The deployed application consists of networking, database, security, authentication, API, reporting, dashboard and monitoring components.


3. Prerequisites

Before starting the deployment, ensure the following are available.

### AWS

- AWS account
- Required permissions for the deployment role
- AWS Region: `ap-south-1`

### GitHub

- CloudMart GitHub repository
- GitHub Actions enabled
- GitHub OIDC configured
- GitHub Actions deployment role configured

### Required GitHub Secrets

The following GitHub repository secrets are required:

- `AWS_ROLE_ARN` – IAM role assumed by GitHub Actions
- `CLOUDMART_DB_PASSWORD` – Database master password used during RDS deployment
- `CLOUDMART_ORDER_EMAIL` – Email address used for order notifications
- `CLOUDMART_LOW_STOCK_EMAIL` – Email address used for low-stock notifications
- `CLOUDMART_MONITORING_EMAIL` – Email address used for CloudWatch monitoring 


4. One-Time CI/CD Bootstrap

### GitHub OIDC Authentication

CloudMart uses GitHub OpenID Connect (OIDC) to allow GitHub Actions to
authenticate with AWS without storing long-lived AWS access keys in GitHub.

The authentication flow is:

GitHub Actions
       ↓
GitHub OIDC token
       ↓
AWS IAM OIDC Identity Provider
       ↓
GitHub Actions Deployment Role
       ↓
Temporary AWS credentials
       ↓
CloudFormation deployment

GitHub Actions assumes the deployment IAM role using the OIDC trust
relationship. AWS validates the OIDC token and, when the configured trust
conditions are satisfied, provides temporary credentials to GitHub Actions.

These temporary credentials are then used by the workflow to deploy the
CloudMart CloudFormation stacks and other AWS resources.


5. Deployment Process
The CloudMart deployment follows this order:
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

The order is important because later stacks depend on resources and outputs created by earlier stages.
________________________________________

6. Step 1 – Network Deployment
The Network stack creates the core networking infrastructure required by CloudMart.
Main components
•	CloudMart VPC 
•	Public subnet 
•	Private subnet(s) 
•	Route tables 
•	Internet connectivity for public resources 
•	VPC endpoints 
•	Security groups

CloudMart VPC
10.0.0.0/16
      |
      +-----------------------------------------------+------------------------------------------------+
      |                                               |                                                |
      v                                               v                                                v 
Public Subnet                                  Private Subnets                     RDS Support Private Subnet
10.0.1.0/24                                      10.0.2.0/24                                     10.0.3.0/24
      |                                                |                                                |            
      |                                                |                                                |
      v                                                v                                                v
EC2 Dashboard                                      Lambda / RDS                         RDS subnet group support


The EC2 dashboard is deployed in the public subnet, while RDS and private application components use the private network.


7. Step 2 – SSM Parameter Configuration
The deployment configures required AWS Systems Manager Parameter Store parameters.
Database-related parameters include:
/cloudmart/<environment>/db/password
/cloudmart/<environment>/db/host
/cloudmart/<environment>/db/port
/cloudmart/<environment>/db/name
/cloudmart/<environment>/db/username
Sensitive values such as the database password are stored as SecureString.
Notification parameters are also used by CloudMart for notification configuration.
Other ssm parameters:
/cloudmart/<environment>/notifications/order-email 
/cloudmart/<environment>/notifications/low-stock-email
/cloudmart/<environment>/monitoring/email

The database password is supplied through the GitHub Secret:
CLOUDMART_DB_PASSWORD
The actual password should never be committed to GitHub.

8. Step 3 – Data Stack Deployment
The Data stack provisions the database and required storage resources.
Main resources
•	Amazon RDS MySQL 
•	Lambda artifact S3 bucket 
•	Reports S3 bucket 
RDS
The CloudMart database is hosted on Amazon RDS for MySQL.
The database is deployed privately and is accessed by the appropriate application components through the configured security groups.
________________________________________
9. Step 4 – Security Stack Deployment
The Security stack creates IAM roles and permissions required by CloudMart.
These roles provide permissions to:
•	Lambda functions 
•	EC2 dashboard 
•	GitHub Actions 
•	Other AWS services used by CloudMart 
IAM policies are configured according to the required service actions and resources.
________________________________________
10. Step 5 – Lambda and Dashboard Artifact Deployment
Before application stacks are deployed, the required application artifacts are uploaded to S3.
The deployment workflow packages and uploads:
product.zip
inventory-alert.zip
order.zip
authorizer.zip
report.zip
schema-runner.zip
The dashboard files are also uploaded:
dashboard/app.py
dashboard/index.html
Lambda packages are stored in the Lambda artifact bucket.
Dashboard files are stored in the Reports bucket under:
cloudmart-dashboard/
The deployment workflow verifies that the uploaded artifacts exist before continuing.




11. Step 6 – Database Schema Deployment
The Schema stack deploys the Schema Runner Lambda.
The Schema Runner applies the CloudMart database schema to RDS.
The database contains:
USERS
PRODUCTS
INVENTORY
ORDERS
ORDER_ITEMS
The schema establishes:
•	Primary keys 
•	Foreign keys 
•	Unique constraints 
•	Required columns 
•	Default values 
•	Referential integrity 
After deployment, the database should be verified to ensure that all required tables exist.


12. Step 7 – Authentication Deployment
The Authentication stack deploys the CloudMart Lambda Authorizer.
The authorizer is responsible for validating authentication information supplied through the API request.
The authorizer uses the configured authentication mechanism to determine whether the request is authorized.




The high-level authentication flow is:
Client
   |
   | Authorization token
   v
API Gateway
   |
   v
Lambda Authorizer
   |
   v
Authentication validation
   |
   v
Allow / Deny

13. Step 8 – API Deployment
The API stack deploys the main CloudMart API components.
Main components
•	API Gateway 
•	Product Lambda 
•	Order Lambda 
•	Inventory Alert Lambda 
•	EventBridge event bus 
•	EventBridge rules 
•	SNS notification integrations 
API Gateway provides the entry point for the application's API operations.
The Product and Order Lambda functions perform the corresponding business operations.
The API Gateway stack contains resources such as:
/products
/products/{id}
/orders
/orders/{id}
The API stack directly integrates API Gateway with the Lambda functions.


14. Step 9 – Reporting Deployment
The Reporting stack deploys the reporting and dashboard components.
Main components
•	Report Generator Lambda 
•	Scheduled EventBridge rule 
•	S3 report storage 
•	EC2 dashboard 
•	Flask application 
•	Gunicorn 
•	Nginx 
Report generation flow
EventBridge Schedule
       |
       | 03:00 UTC
       | 08:30 IST
       v
Report Generator Lambda
       |
       v
RDS MySQL
       |
       v
Generate CSV Report
       |
       v
S3 Reports Bucket
       |
       v
Dashboard
The generated reports are stored under:
reports/
The dashboard retrieves the available reports from the S3 bucket.


15. Dashboard Deployment
The CloudMart dashboard is hosted on an EC2 instance.
The application flow is:
User Browser
     |
     v
Nginx
     |
     v
Gunicorn
     |
     v
Flask Application
     |
     v
RDS MySQL / S3
Dashboard components
•	Flask 
•	Gunicorn 
•	Nginx 
•	HTML/CSS/JavaScript 
•	RDS MySQL 
•	S3 reports 
The dashboard requires authentication before accessing protected dashboard functionality.
________________________________________
16. Step 10 – Monitoring Deployment
The Monitoring stack provisions CloudWatch monitoring resources.
Monitoring includes
•	CloudWatch dashboard 
•	Lambda metrics 
•	API Gateway metrics 
•	RDS metrics 
•	CloudWatch alarms 
•	SNS notification topic 
•	Email notification 
Lambda metrics
The monitoring design includes metrics for the CloudMart Lambda functions, including:
•	Invocations 
•	Errors 
•	Duration 
•	Throttles 
•	Concurrent executions 
API Gateway metrics
The dashboard monitors:
•	Request count 
•	4XX errors 
•	5XX errors 
RDS metrics
The monitoring includes:
•	CPU utilization 
•	Database connections 
•	Free storage 
________________________________________
17. Alarm Notification Flow
CloudWatch alarms use SNS for notification delivery.
Application / AWS Service
          |
          v
     CloudWatch
       Metric
          |
          v
    CloudWatch Alarm
          |
       Alarm State
          |
          v
          SNS
          |
          v
       Email
For example, when an order-related alarm crosses its configured threshold:
Order processing
      ↓
CloudWatch metric
      ↓
Alarm threshold exceeded
      ↓
Alarm enters ALARM state
      ↓
SNS notification
      ↓
Configured email
________________________________________
18. Post-Deployment Verification
After GitHub Actions completes successfully, verify each major component.
18.1 CloudFormation
Verify that the following stacks are successfully deployed:
cloudmart-<environment>-network
cloudmart-<environment>-data
cloudmart-<environment>-security
cloudmart-<environment>-schema
cloudmart-<environment>-auth
cloudmart-<environment>-api
cloudmart-<environment>-reporting
cloudmart-<environment>-monitoring
Expected state:
CREATE_COMPLETE
or:
UPDATE_COMPLETE
________________________________________
19. Database Verification
Verify that RDS is available.
Check that the following tables exist:
users
products
inventory
orders
order_items
Verify relationships and sample data as required.
Also verify that inventory and order operations are correctly reflected in the database.
________________________________________
20. Lambda Verification
Verify that the required Lambda functions exist:
CloudMart-<environment>-ProductLambda
CloudMart-<environment>-OrderLambda
CloudMart-<environment>-InventoryAlert
CloudMart-<environment>-Authorizer
CloudMart-<environment>-ReportGenerator
CloudMart-<environment>-SchemaRunner
Check CloudWatch Logs for successful initialization and execution.
________________________________________
21. API Verification
Verify the API Gateway deployment and stage.
Test the major operations:
Products
GET
POST
PUT
DELETE
Orders
POST
GET
PATCH – cancellation
Verify both successful and validation/error scenarios.
________________________________________
22. EventBridge Verification
Verify:
•	CloudMart EventBridge event bus exists 
•	Order event rules are enabled 
•	Order confirmation notification works 
•	Order failure notification works 
•	Order cancellation notification works 
•	Daily report schedule is enabled 
The daily report schedule runs at:
03:00 UTC
08:30 IST
________________________________________
23. SNS Verification
Verify that:
•	Required SNS topics exist 
•	Email subscriptions are confirmed 
•	Notifications are delivered when the corresponding events occur 
Test at least one notification path where appropriate.
________________________________________
24. S3 Verification
Verify that:
Lambda artifacts
The required Lambda packages exist in the Lambda artifact bucket.
Dashboard
The following files exist:
cloudmart-dashboard/app.py
cloudmart-dashboard/index.html
Reports
Generated reports appear under:
reports/
________________________________________
25. Dashboard Verification
Verify:
1.	EC2 instance is running. 
2.	Nginx service is running. 
3.	Gunicorn service is running. 
4.	Flask application is running. 
5.	Dashboard login page loads. 
6.	Admin authentication works. 
7.	Dashboard KPI values load. 
8.	Product/order/user/inventory data is displayed. 
9.	Reports are visible. 
10.	Report download works. 
________________________________________
26. Monitoring Verification
Verify that CloudWatch metrics are being populated.
Check:
Lambda Invocations
Lambda Errors
Lambda Duration
Lambda Throttles
Lambda Concurrent Executions

API Gateway Count
API Gateway 4XX
API Gateway 5XX

RDS CPU
RDS Connections
RDS Free Storage
Also verify the CloudWatch dashboard and configured alarms.
________________________________________
27. Functional Smoke Test
After deployment, perform a basic end-to-end test.
Product flow
Create Product
      ↓
Product stored in RDS
      ↓
Retrieve Product
      ↓
Update Product
      ↓
Delete Product
Order flow
Create Order
      ↓
Validate Product
      ↓
Check Inventory
      ↓
Create Order
      ↓
Update Inventory
      ↓
Publish Event
      ↓
Notification
Cancellation flow
Cancel Order
      ↓
Update Order Status
      ↓
Restore Inventory
      ↓
Publish Cancellation Event
      ↓
SNS Notification
Low-stock flow
Inventory decreases
      ↓
Stock reaches threshold
      ↓
Inventory Alert
      ↓
SNS
      ↓
Email
________________________________________
28. Reporting Smoke Test
Verify the daily reporting flow:
EventBridge
      ↓
Report Generator Lambda
      ↓
Read RDS data
      ↓
Generate CSV
      ↓
Upload to S3
      ↓
Dashboard displays report
Verify that a report exists in the S3 reports/ prefix after successful report generation.
________________________________________
29. Troubleshooting
Issue	Check
CloudFormation stack failed	CloudFormation Events
Lambda execution failed	Lambda CloudWatch Logs
Database connection failed	RDS status, Security Groups, SSM parameters
API returns 500	API Gateway + Lambda logs
API authorization fails	Authorizer Lambda + API Gateway configuration
Dashboard unavailable	EC2, Nginx and Gunicorn status
Dashboard shows old code	S3 dashboard files and EC2 deployed files
Report not generated	EventBridge rule, Report Lambda logs and S3
No alarm email	Alarm state and SNS subscription
No metric visible	Lambda metric publishing and CloudWatch
________________________________________
30. Deployment Failure Handling
If a deployment fails:
GitHub Actions
      ↓
Deployment failure
      ↓
Identify failed CloudFormation stack
      ↓
Check CloudFormation Events
      ↓
Check related CloudWatch Logs
      ↓
Fix configuration/code
      ↓
Commit changes
      ↓
Run deployment again

The failed resource should be identified before attempting to redeploy.


31.Deployment Summary
CloudMart uses an automated CI/CD deployment process where GitHub Actions authenticates to AWS using GitHub OIDC and deploys the application infrastructure through AWS CloudFormation.
The deployment is performed in dependency order, beginning with networking and continuing through database, security, application, reporting and monitoring components.
After deployment, each major AWS service and application flow is verified through CloudFormation status checks, functional tests, monitoring checks and notification tests.
