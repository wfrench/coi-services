#!/usr/bin/env python

__author__ = 'Stephen P. Henrie, Raj Singh'
__license__ = 'Apache 2.0'

import unittest, os
import gevent
import simplejson
import ast
from mock import patch
import logging
from pyon.net.endpoint import Subscriber
from interface.services.cei.iprocess_dispatcher_service import ProcessDispatcherServiceProcessClient
from interface.services.coi.iresource_registry_service import ResourceRegistryServiceProcessClient
from interface.services.dm.iingestion_management_service import IngestionManagementServiceProcessClient
from interface.services.dm.ipubsub_management_service import PubsubManagementServiceProcessClient
from interface.services.dm.idataset_management_service import DatasetManagementServiceProcessClient
from interface.services.sa.idata_product_management_service import DataProductManagementServiceProcessClient
from interface.services.sa.idata_process_management_service import DataProcessManagementServiceProcessClient
from interface.services.sa.iinstrument_management_service import InstrumentManagementServiceProcessClient
from interface.services.sa.idata_acquisition_management_service import DataAcquisitionManagementServiceProcessClient
from interface.services.dm.idata_retriever_service import DataRetrieverServiceProcessClient
from interface.services.ans.ivisualization_service import VisualizationServiceProcessClient
from ion.services.ans.visualization_service import USER_VISUALIZATION_QUEUE
from prototype.sci_data.stream_defs import SBE37_CDM_stream_definition

from pyon.public import log, IonObject, RT, PRED, CFG
from ion.services.ans.test.test_helper import VisualizationIntegrationTestHelper, preload_ion_params

from nose.plugins.attrib import attr

from ion.services.dm.utility.granule.record_dictionary import RecordDictionaryTool
from pyon.util.containers import get_safe

from pyon.util.context import LocalContextMixin

from ion.services.ans.visualization_service import USER_VISUALIZATION_QUEUE


class VisualizationServiceTestProcess(LocalContextMixin):
    name = 'visualization_test'
    id='visualization_int_test'
    process_type = 'simple'

@attr('INT', group='as')
class TestVisualizationServiceIntegration(VisualizationIntegrationTestHelper):

    def setUp(self):
        # Start container

        logging.disable(logging.ERROR)
        self._start_container()
        self.container.start_rel_from_url('res/deploy/r2deploy.yml')
        # simulate preloading
        preload_ion_params(self.container)
        logging.disable(logging.NOTSET)

        #Instantiate a process to represent the test
        process=VisualizationServiceTestProcess()

        # Now create client to DataProductManagementService
        self.rrclient = ResourceRegistryServiceProcessClient(node=self.container.node, process=process)
        self.damsclient = DataAcquisitionManagementServiceProcessClient(node=self.container.node, process=process)
        self.pubsubclient =  PubsubManagementServiceProcessClient(node=self.container.node, process=process)
        self.ingestclient = IngestionManagementServiceProcessClient(node=self.container.node, process=process)
        self.imsclient = InstrumentManagementServiceProcessClient(node=self.container.node, process=process)
        self.dataproductclient = DataProductManagementServiceProcessClient(node=self.container.node, process=process)
        self.dataprocessclient = DataProcessManagementServiceProcessClient(node=self.container.node, process=process)
        self.datasetclient =  DatasetManagementServiceProcessClient(node=self.container.node, process=process)
        self.process_dispatcher = ProcessDispatcherServiceProcessClient(node=self.container.node, process=process)
        self.data_retriever = DataRetrieverServiceProcessClient(node=self.container.node, process=process)
        self.vis_client = VisualizationServiceProcessClient(node=self.container.node, process=process)

        self.ctd_stream_def = SBE37_CDM_stream_definition()

    def validate_messages(self, msgs):
        msg = msgs


        rdt = RecordDictionaryTool.load_from_granule(msg.body)

        vardict = {}
        vardict['temp'] = get_safe(rdt, 'temp')
        vardict['time'] = get_safe(rdt, 'time')
        print vardict['time']
        print vardict['temp']




    @attr('LOCOINT')
    #@patch.dict('pyon.ion.exchange.CFG', {'container':{'exchange':{'auto_register': False}}})
    @unittest.skipIf(os.getenv('CEI_LAUNCH_TEST', False),'Not integrated for CEI')
    def test_visualization_queue(self):

        #The list of data product streams to monitor
        data_product_stream_ids = list()

        #Create the input data product
        ctd_stream_id, ctd_parsed_data_product_id = self.create_ctd_input_stream_and_data_product()
        data_product_stream_ids.append(ctd_stream_id)

        user_queue_name = USER_VISUALIZATION_QUEUE

        xq = self.container.ex_manager.create_xn_queue(user_queue_name)

        salinity_subscription_id = self.pubsubclient.create_subscription(
            stream_ids=data_product_stream_ids,
            exchange_name = user_queue_name,
            name = "user visualization queue"
        )

        subscriber = Subscriber(from_name=xq)
        subscriber.initialize()

        # after the queue has been created it is safe to activate the subscription
        self.pubsubclient.activate_subscription(subscription_id=salinity_subscription_id)

        #Start the output stream listener to monitor and collect messages
        #results = self.start_output_stream_and_listen(None, data_product_stream_ids)

        #Not sure why this is needed - but it is
        #subscriber._chan.stop_consume()

        ctd_sim_pid = self.start_simple_input_stream_process(ctd_stream_id)
        gevent.sleep(10.0)  # Send some messages - don't care how many

        msg_count,_ = xq.get_stats()
        log.info('Messages in user queue 1: %s ' % msg_count)

        #Validate the data from each of the messages along the way
        #self.validate_messages(results)

#        for x in range(msg_count):
#            mo = subscriber.get_one_msg(timeout=1)
#            print mo.body
#            mo.ack()

        msgs = subscriber.get_all_msgs(timeout=2)
        for x in range(len(msgs)):
            msgs[x].ack()
            self.validate_messages(msgs[x])
           # print msgs[x].body



        #Should be zero after pulling all of the messages.
        msg_count,_ = xq.get_stats()
        log.info('Messages in user queue 2: %s ' % msg_count)


        #Trying to continue to receive messages in the queue
        gevent.sleep(5.0)  # Send some messages - don't care how many


        #Turning off after everything - since it is more representative of an always on stream of data!
        self.process_dispatcher.cancel_process(ctd_sim_pid) # kill the ctd simulator process - that is enough data



        #Should see more messages in the queue
        msg_count,_ = xq.get_stats()
        log.info('Messages in user queue 3: %s ' % msg_count)

        msgs = subscriber.get_all_msgs(timeout=2)
        for x in range(len(msgs)):
            msgs[x].ack()
            self.validate_messages(msgs[x])

        #Should be zero after pulling all of the messages.
        msg_count,_ = xq.get_stats()
        log.info('Messages in user queue 4: %s ' % msg_count)

        subscriber.close()
        self.container.ex_manager.delete_xn(xq)




    @patch.dict(CFG, {'user_queue_monitor_timeout': 5})
    def test_realtime_visualization(self):

#        #Start up multiple vis service workers if not a CEI launch
#        if not os.getenv('CEI_LAUNCH_TEST', False):
#            vpid1 = self.container.spawn_process('visualization_service1','ion.services.ans.visualization_service','VisualizationService', CFG )
#            self.addCleanup(self.container.terminate_process, vpid1)
#            vpid2 = self.container.spawn_process('visualization_service2','ion.services.ans.visualization_service','VisualizationService', CFG )
#            self.addCleanup(self.container.terminate_process, vpid2)

        ## Create the Highcharts workflow definition since there is no preload for the test
        #workflow_def_id = self.create_highcharts_workflow_def()

        #Create the input data product
        ctd_stream_id, ctd_parsed_data_product_id = self.create_ctd_input_stream_and_data_product()
        ctd_sim_pid = self.start_sinusoidal_input_stream_process(ctd_stream_id)

        vis_params ={}
        vis_token_resp = self.vis_client.initiate_realtime_visualization_data(data_product_id=ctd_parsed_data_product_id, visualization_parameters=simplejson.dumps(vis_params))
        vis_token = ast.literal_eval(vis_token_resp)["rt_query_token"]

        result = gevent.event.AsyncResult()

        def get_vis_messages(get_data_count=7):  #SHould be an odd number for round robbin processing by service workers


            get_cnt = 0
            while get_cnt < get_data_count:

                vis_data = self.vis_client.get_realtime_visualization_data(vis_token)
                if (vis_data):
                    self.validate_highcharts_transform_results(vis_data)

                get_cnt += 1
                gevent.sleep(5) # simulates the polling from UI

            result.set(get_cnt)

        gevent.spawn(get_vis_messages)

        result.get(timeout=90)

        #Trying to continue to receive messages in the queue
        gevent.sleep(2.0)  # Send some messages - don't care how many


        # Cleanup
        self.vis_client.terminate_realtime_visualization_data(vis_token)


        #Turning off after everything - since it is more representative of an always on stream of data!
        self.process_dispatcher.cancel_process(ctd_sim_pid) # kill the ctd simulator process - that is enough data

    @patch.dict(CFG, {'user_queue_monitor_timeout': 5})
    @patch.dict(CFG, {'user_queue_monitor_size': 25})
    @attr('CLEANUP')
    @unittest.skipIf(os.getenv('PYCC_MODE', False),'Not integrated for CEI')
    def test_realtime_visualization_cleanup(self):

#        #Start up multiple vis service workers if not a CEI launch
#        if not os.getenv('CEI_LAUNCH_TEST', False):
#            vpid1 = self.container.spawn_process('visualization_service1','ion.services.ans.visualization_service','VisualizationService', CFG )
#            self.addCleanup(self.container.terminate_process, vpid1)
#            vpid2 = self.container.spawn_process('visualization_service2','ion.services.ans.visualization_service','VisualizationService', CFG )
#            self.addCleanup(self.container.terminate_process, vpid2)

        #get the list of queues and message counts on the broker for the user vis queues
        try:
            queues = self.container.ex_manager.list_queues(name=USER_VISUALIZATION_QUEUE, return_columns=['name', 'messages'])
            q_names = [ q['name'] for q in queues if q['name']] #Get a list of only the queue names
            original_queue_count = len(q_names)
        except Exception, e:
            log.warn('Unable to get queue information from broker management plugin: ' + e.message)
            pass

        ## Create the highcharts workflow definition since there is no preload for the test
        #workflow_def_id = self.create_highcharts_workflow_def()

        #Create the input data product
        ctd_stream_id, ctd_parsed_data_product_id = self.create_ctd_input_stream_and_data_product()
        ctd_sim_pid = self.start_sinusoidal_input_stream_process(ctd_stream_id)


        #Start up a number of requests - and queues - to start accumulating messages. THe test will not clean them up
        #but instead check to see if the monitoring thread will.
        vis_token_resp = self.vis_client.initiate_realtime_visualization_data(data_product_id=ctd_parsed_data_product_id)
        bad_vis_token1 = ast.literal_eval(vis_token_resp)["rt_query_token"]

        vis_token_resp = self.vis_client.initiate_realtime_visualization_data(data_product_id=ctd_parsed_data_product_id)
        bad_vis_token2 = ast.literal_eval(vis_token_resp)["rt_query_token"]

        vis_token_resp = self.vis_client.initiate_realtime_visualization_data(data_product_id=ctd_parsed_data_product_id)
        bad_vis_token3 = ast.literal_eval(vis_token_resp)["rt_query_token"]

        vis_token_resp = self.vis_client.initiate_realtime_visualization_data(data_product_id=ctd_parsed_data_product_id)
        vis_token = ast.literal_eval(vis_token_resp)["rt_query_token"]

        #Get the default exchange space
        exchange = self.container.ex_manager.default_xs.exchange


        #get the list of queues and message counts on the broker for the user vis queues
        try:
            queues = self.container.ex_manager.list_queues(name=USER_VISUALIZATION_QUEUE, return_columns=['name', 'messages'])
            q_names = [ q['name'] for q in queues if q['name']] #Get a list of only the queue names

            self.assertIn(exchange + "." + bad_vis_token1, q_names)
            self.assertIn(exchange + "." + bad_vis_token2, q_names)
            self.assertIn(exchange + "." + bad_vis_token3, q_names)
            self.assertIn(exchange + "." + vis_token, q_names)

        except Exception, e:
            log.warn('Unable to get queue information from broker management plugin: ' + e.message)
            pass

        result = gevent.event.AsyncResult()

        def get_vis_messages(get_data_count=7):  #SHould be an odd number for round robbin processing by service workers


            get_cnt = 0
            while get_cnt < get_data_count:

                vis_data = self.vis_client.get_realtime_visualization_data(vis_token)
                if (vis_data):
                    self.validate_highcharts_transform_results(vis_data)

                get_cnt += 1
                gevent.sleep(5) # simulates the polling from UI

            result.set(get_cnt)

        gevent.spawn(get_vis_messages)

        result.get(timeout=90)

        #Trying to continue to receive messages in the queue
        gevent.sleep(2.0)  # Send some messages - don't care how many

        try:
            #get the list of queues and message counts on the broker for the user vis queues
            queues = self.container.ex_manager.list_queues(name=USER_VISUALIZATION_QUEUE, return_columns=['name', 'messages'])
            q_names = [ q['name'] for q in queues if q['name']] #Get a list of only the queue names

            self.assertNotIn(exchange + "." + bad_vis_token1, q_names)
            self.assertNotIn(exchange + "." + bad_vis_token2, q_names)
            self.assertNotIn(exchange + "." + bad_vis_token3, q_names)
            self.assertIn(exchange + "." + vis_token, q_names)

            # Cleanup
            self.vis_client.terminate_realtime_visualization_data(vis_token)

            queues = self.container.ex_manager.list_queues(name=USER_VISUALIZATION_QUEUE, return_columns=['name', 'messages'])
            q_names = [ q['name'] for q in queues if q['name']] #Get a list of only the queue names

            self.assertNotIn(exchange + "." + vis_token, q_names)

            self.assertEqual(original_queue_count,len(q_names))
        except Exception, e:
            log.warn('Unable to get queue information from broker management plugin: ' + e.message)
            pass

        #Turning off after everything - since it is more representative of an always on stream of data!
        self.process_dispatcher.cancel_process(ctd_sim_pid) # kill the ctd simulator process - that is enough data



