"""
Copyright 2017-present, Airbnb Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
# pylint: disable=abstract-class-instantiated,attribute-defined-outside-init
import boto3
from mock import patch
from moto import mock_s3, mock_lambda, mock_kinesis
from nose.tools import (
    assert_equal,
    assert_false,
    assert_is_not_none,
    assert_true
)

from stream_alert.alert_processor.outputs.output_base import (
    OutputProperty,
    StreamAlertOutput
)
from stream_alert.alert_processor.outputs import aws
from stream_alert_cli.helpers import create_lambda_function
from tests.unit.stream_alert_alert_processor import CONFIG, FUNCTION_NAME, REGION
from tests.unit.stream_alert_alert_processor.helpers import get_alert


class TestAWSOutput(object):
    """Test class for AWSOutput Base"""

    @staticmethod
    @patch.object(aws.AWSOutput, '__service__', 'aws-s3')
    def test_aws_format_output_config():
        """AWSOutput - Format Output Config"""
        props = {
            'descriptor': OutputProperty(
                'short_descriptor',
                'descriptor_value'),
            'aws_value': OutputProperty(
                'unique arn value, bucket, etc',
                'bucket.value')}

        formatted_config = aws.AWSOutput.format_output_config(CONFIG, props)

        assert_equal(len(formatted_config), 2)
        assert_is_not_none(formatted_config.get('descriptor_value'))
        assert_is_not_none(formatted_config.get('unit_test_bucket'))


class TestS3Ouput(object):
    """Test class for S3Output"""
    @classmethod
    def setup_class(cls):
        """Setup the class before any methods"""
        cls.__service = 'aws-s3'
        cls.__descriptor = 'unit_test_bucket'
        cls.__dispatcher = StreamAlertOutput.create_dispatcher(cls.__service,
                                                               REGION,
                                                               FUNCTION_NAME,
                                                               CONFIG)

    @classmethod
    def teardown_class(cls):
        """Teardown the class after all methods"""
        cls.dispatcher = None

    def test_locals(self):
        """S3Output local variables"""
        assert_equal(self.__dispatcher.__class__.__name__, 'S3Output')
        assert_equal(self.__dispatcher.__service__, self.__service)

    def _setup_dispatch(self):
        """Helper for setting up S3Output dispatch"""
        bucket = CONFIG[self.__service][self.__descriptor]
        boto3.client('s3', region_name=REGION).create_bucket(Bucket=bucket)

        return get_alert()

    @patch('logging.Logger.info')
    @mock_s3
    def test_dispatch(self, log_mock):
        """S3Output dispatch"""
        alert = self._setup_dispatch()
        self.__dispatcher.dispatch(descriptor=self.__descriptor,
                                   rule_name='rule_name',
                                   alert=alert)

        log_mock.assert_called_with('Successfully sent alert to %s', self.__service)


class TestFirehoseOutput(object):
    """Test class for AWS Kinesis Firehose"""
    @classmethod
    def setup_class(cls):
        """Setup the class before any methods"""
        cls.__service = 'aws-firehose'
        cls.__descriptor = 'unit_test_delivery_stream'
        cls.__dispatcher = StreamAlertOutput.create_dispatcher(cls.__service,
                                                               REGION,
                                                               FUNCTION_NAME,
                                                               CONFIG)

    @classmethod
    def teardown_class(cls):
        """Teardown the class after all methods"""
        cls.dispatcher = None

    def test_locals(self):
        """Output local variables - Kinesis Firehose"""
        assert_equal(self.__dispatcher.__class__.__name__, 'KinesisFirehoseOutput')
        assert_equal(self.__dispatcher.__service__, self.__service)

    def _setup_dispatch(self):
        """Helper for setting up S3Output dispatch"""
        delivery_stream = CONFIG[self.__service][self.__descriptor]
        boto3.client('firehose', region_name=REGION).create_delivery_stream(
            DeliveryStreamName=delivery_stream,
            S3DestinationConfiguration={
                'RoleARN': 'arn:aws:iam::123456789012:role/firehose_delivery_role',
                'BucketARN': 'arn:aws:s3:::unit_test',
                'Prefix': '/',
                'BufferingHints': {
                    'SizeInMBs': 128,
                    'IntervalInSeconds': 128
                },
                'CompressionFormat': 'GZIP',
            }
        )

        return get_alert()

    @patch('logging.Logger.info')
    @mock_kinesis
    def test_dispatch(self, log_mock):
        """Output Dispatch - Kinesis Firehose"""
        alert = self._setup_dispatch()
        resp = self.__dispatcher.dispatch(descriptor=self.__descriptor,
                                          rule_name='rule_name',
                                          alert=alert)

        assert_true(resp)
        log_mock.assert_called_with('Successfully sent alert to %s', self.__service)

    @mock_kinesis
    def test_dispatch_ignore_large_payload(self):
        """Output Dispatch - Kinesis Firehose with Large Payload"""
        alert = self._setup_dispatch()
        alert['record'] = 'test' * 1000 * 1000
        resp = self.__dispatcher.dispatch(descriptor=self.__descriptor,
                                          rule_name='rule_name',
                                          alert=alert)

        assert_false(resp)



class TestLambdaOuput(object):
    """Test class for LambdaOutput"""
    @classmethod
    def setup_class(cls):
        """Setup the class before any methods"""
        cls.__service = 'aws-lambda'
        cls.__descriptor = 'unit_test_lambda'
        cls.__dispatcher = StreamAlertOutput.create_dispatcher(cls.__service,
                                                               REGION,
                                                               FUNCTION_NAME,
                                                               CONFIG)

    @classmethod
    def teardown_class(cls):
        """Teardown the class after all methods"""
        cls.dispatcher = None

    def test_locals(self):
        """LambdaOutput local variables"""
        assert_equal(self.__dispatcher.__class__.__name__, 'LambdaOutput')
        assert_equal(self.__dispatcher.__service__, self.__service)

    def _setup_dispatch(self, alt_descriptor=''):
        """Helper for setting up LambdaOutput dispatch"""
        function_name = CONFIG[self.__service][alt_descriptor or self.__descriptor]
        create_lambda_function(function_name, REGION)
        return get_alert()

    @mock_lambda
    @patch('logging.Logger.info')
    def test_dispatch(self, log_mock):
        """LambdaOutput dispatch"""
        alert = self._setup_dispatch()
        self.__dispatcher.dispatch(descriptor=self.__descriptor,
                                   rule_name='rule_name',
                                   alert=alert)

        log_mock.assert_called_with('Successfully sent alert to %s', self.__service)

    @mock_lambda
    @patch('logging.Logger.info')
    def test_dispatch_with_qualifier(self, log_mock):
        """LambdaOutput dispatch with qualifier"""
        alt_descriptor = '{}_qual'.format(self.__descriptor)
        alert = self._setup_dispatch(alt_descriptor)
        self.__dispatcher.dispatch(descriptor=alt_descriptor,
                                   rule_name='rule_name',
                                   alert=alert)

        log_mock.assert_called_with('Successfully sent alert to %s', self.__service)
