"""Pulumi program to generate infrastructure for Data pipeline"""

import pulumi
from pulumi_gcp import storage
from pulumi_gcp import dataflow
from pulumi_gcp import bigquery
from pulumi_gcp import serviceaccount
import pulumi_gcp as gcp


#Use classes to define/declare your modules

class DataFlow:
    """
    All infrastructure related to DataFlow is specified within this class. This include staging buckets and bucket that
    store job templates

    Eg:

    # Create a GCP resource (Storage Bucket)
    ftemplate_bucket = storage.Bucket('flex-template-bucket', location="US")
    jt_bucket = storage.Bucket('job-temp-bucket', location="US")
    jtemplate_bucket = storage.Bucket('job-template-bucket', location="US")

    # Create a Flex Dataflow Job 
    flextemplate = dataflow.FlexTemplateJob(resource_name='flex1', container_spec_gcs_path=ftemplate_bucket.url)
    job = dataflow.Job(resource_name='job1', temp_gcs_location=jt_bucket.url, template_gcs_path=jtemplate_bucket.url)

    """
    def __init__(self, env:str, job:str, location:str="US") -> None:
        self.flex_template_bucket_name = f'ft_{env}_{job}'
        self.location = location
        self.job_temp_bucket_name = f'job-temp-bucket_{env}_{job}'
    
    # This method defines the resources to be created
    def createInfra(self,gcs_account, account):
        # Create a GCP resource (Storage Bucket)
        self.ftemplate_bucket = storage.Bucket(self.flex_template_bucket_name , location=self.location)
        self.jt_bucket = storage.Bucket('job-temp-bucket', location=self.location)
        self.jtemplate_bucket = storage.Bucket('job-template-bucket', location="US")
        # Create a Flex Dataflow Job 
        self.flextemplate = dataflow.FlexTemplateJob(resource_name='flex1', container_spec_gcs_path=self.ftemplate_bucket.url)
        self.job = dataflow.Job(resource_name='job1', temp_gcs_location=self.jt_bucket.url, template_gcs_path=self.jtemplate_bucket.url)

        # Scheduler
        self.job = gcp.cloudscheduler.Job("job",
            description="test http job",
            schedule="*/8 * * * *",
            time_zone="America/New_York",
            attempt_deadline="320s",
            http_target=gcp.cloudscheduler.JobHttpTargetArgs(
                http_method="GET",
                uri="https://example.com/ping",
                oidc_token=gcp.cloudscheduler.JobHttpTargetOidcTokenArgs(
                    service_account_email=account.email,
                ),
            ))

        self.outputs()

    # This method specifies the outputs
    def outputs(self):
        pulumi.export('flex_template_bucket__name', self.ftemplate_bucket.url)
        pulumi.export('flex_template_bucket__name', self.jt_bucket.url)


class Bigquery:

    """
    This class encapsulates all the infrastructure related to bigquery

    Eg:
        # Create bigquery
        connection = bigquery.Connection("connection",
        cloud_resource=bigquery.ConnectionCloudResourceArgs(),
        connection_id="my-connection",
        description="a riveting description",
        friendly_name="👋",
        location="US")
    """
    def __init__(self, env:str, connection_id:str, description:str="Big query connection", friendly_name:str="👋", location:str="US") -> None:
        self.connectionName = f'connection_{env}'
        self.connectionId = connection_id
        self.description = description
        self.friendly_name = friendly_name
        self.location = location

    def createInfra(self):
        # Create bigquery
        connection = bigquery.Connection("connection",
        cloud_resource=bigquery.ConnectionCloudResourceArgs(),
        connection_id=self.connectionId,
        description=self.description,
        friendly_name=self.friendly_name,
        location=self.location)

    def outputs(self):
        pulumi.export('connection_name', self.connectionName)


class CloudFunctions:
    def __init__(self) -> None:
        pass

    def infra(self, gcs_account, account):
        # Create cloudfunctions 
        source_bucket = gcp.storage.Bucket("source-bucket",
            location="US",
            uniform_bucket_level_access=True)
        object = gcp.storage.BucketObject("object",
            bucket=source_bucket.name,
            source=pulumi.FileAsset("function-source.zip"))

        # Add path to the zipped function source code
        trigger_bucket = gcp.storage.Bucket("trigger-bucket",   
            location="us-central1",
            uniform_bucket_level_access=True)



        gcs_pubsub_publishing = gcp.projects.IAMMember("gcs-pubsub-publishing",
            project="my-project-name",
            role="roles/pubsub.publisher",
            member=f"serviceAccount:{gcs_account.email_address}")

        # Permissions on the service account used by the function and Eventarc trigger
        invoking = gcp.projects.IAMMember("invoking",
            project="my-project-name",
            role="roles/run.invoker",
            member=account.email.apply(lambda email: f"serviceAccount:{email}"),
            opts=pulumi.ResourceOptions(depends_on=[gcs_pubsub_publishing]))

        # Handle IAM and permissions
        event_receiving = gcp.projects.IAMMember("event-receiving",
            project="my-project-name",
            role="roles/eventarc.eventReceiver",
            member=account.email.apply(lambda email: f"serviceAccount:{email}"),
            opts=pulumi.ResourceOptions(depends_on=[invoking]))
        artifactregistry_reader = gcp.projects.IAMMember("artifactregistry-reader",
            project="my-project-name",
            role="roles/artifactregistry.reader",
            member=account.email.apply(lambda email: f"serviceAccount:{email}"),
            opts=pulumi.ResourceOptions(depends_on=[event_receiving]))


        # Actual function
        function = gcp.cloudfunctionsv2.Function("function",
            location="us-central1",
            description="a new function",
            build_config=gcp.cloudfunctionsv2.FunctionBuildConfigArgs(
                runtime="nodejs12",
                entry_point="entryPoint",
                environment_variables={
                    "BUILD_CONFIG_TEST": "build_test",
                },
                source=gcp.cloudfunctionsv2.FunctionBuildConfigSourceArgs(
                    storage_source=gcp.cloudfunctionsv2.FunctionBuildConfigSourceStorageSourceArgs(
                        bucket=source_bucket.name,
                        object=object.name,
                    ),
                ),
            ),
            service_config=gcp.cloudfunctionsv2.FunctionServiceConfigArgs(
                max_instance_count=3,
                min_instance_count=1,
                available_memory="256M",
                timeout_seconds=60,
                environment_variables={
                    "SERVICE_CONFIG_TEST": "config_test",
                },
                ingress_settings="ALLOW_INTERNAL_ONLY",
                all_traffic_on_latest_revision=True,
                service_account_email=account.email,
            ),
            event_trigger=gcp.cloudfunctionsv2.FunctionEventTriggerArgs(
                trigger_region="us-central1",
                event_type="google.cloud.storage.object.v1.finalized",
                retry_policy="RETRY_POLICY_RETRY",
                service_account_email=account.email,
                event_filters=[gcp.cloudfunctionsv2.FunctionEventTriggerEventFilterArgs(
                    attribute="bucket",
                    value=trigger_bucket.name,
                )],
            ),
            opts=pulumi.ResourceOptions(depends_on=[
                    event_receiving,
                    artifactregistry_reader,
                ]))


class Logging:
    def __init__(self) -> None:
        pass

    def infra(self):
        # Logging
        basic = gcp.logging.ProjectBucketConfig("basic",
            project="my-project-name",
            location="global",
            retention_days=30,
            bucket_id="_Default")

        primary = gcp.logging.LogView("primary",
            bucket=basic.id,
            description="A logging view configured with Terraform",
            filter="SOURCE(\"projects/myproject\") AND resource.type = \"gce_instance\" AND LOG_ID(\"stdout\")")


class ServiceAccount():
    def __init__(self) -> None:
        pass

    def createInfra():
        return None

# Consuming Modules through the main function
def main():

    #TODO Can move to a seperate class
    gcs_account = gcp.storage.get_project_service_account()

    account = gcp.serviceaccount.Account("account",
            account_id="gcf-sa",
            display_name="Test Service Account - used for both the cloud function and eventarc trigger in the test")

    #Create One or more Cloud Functions
    cf = CloudFunctions()
    cf.infra(gcs_account, account)


    df = DataFlow(env="dev", job="job1")
    df.createInfra(gcs_account,account)
    #Create One or more Cloud Storage


if __name__ == "__main__":
    main()

#TODO You can also use the pulumi automation api and integrate with a python backend such as fastapi
#Then the infra creation process can be initiated with a rest api call.
# Bust simple would be use pulumi up.





