import random

from flask import jsonify

from lsapi.helper.api_exceptions import InternalProcessingException, BadRequestException
from lsapi.helper.result_manipulations import \
    identity, \
    make_public_downtime, \
    make_public_comment, \
    make_public_host, \
    make_public_service, \
    comments2array, \
    downtimes2array, \
    cast_fields


class LivestatusAction:
    public_functions = {
        "hosts": make_public_host,
        "services": make_public_service,
        "downtimes": make_public_downtime,
        "comments": make_public_comment,
        "columns": identity
    }

    def __init__(self, data, return_code):
        self.data = data
        self.return_code = return_code
        # get entity
        entities = [entity for entity in data]
        if len(entities) != 1:
            raise InternalProcessingException("result data contains more than one key", status_code=500)
        else:
            self.entity = entities[0]
        # determine if we got a single element or array
        if len(self.data[self.entity]) > 1:
            self.single = False
        else:
            self.single = True
        # set make_public function
        try:
            self.make_public_function = self.public_functions[entity]
        except KeyError:
            self.make_public_function = identity

    def __str__(self):
        return "Task Instance for %s with return code %d" % (self.entity, self.return_code)

    def return_table(self):
        public_data = {}
        if self.return_code == 200:
            public_data[self.entity] = [cast_fields(element) for element in self.data[self.entity]]
            public_data[self.entity] = [self.make_public_function(element) for element in public_data[self.entity]]
            public_data[self.entity] = [downtimes2array(element) for element in public_data[self.entity]]
            public_data[self.entity] = [comments2array(element) for element in public_data[self.entity]]
            if self.single:
                return jsonify(public_data[self.entity][0]), self.return_code
            else:
                return jsonify(public_data), self.return_code
        else:
            return jsonify(self.data), self.return_code

    def set_downtime(self, ls_query_instance, downtime_data):
        try:
            # check if POST json contains a key 'downtime'
            downtime_data = downtime_data['downtime']
            # TODO: add downtime data validation (start/end/author
            # add a downtime identifier
            downtime_identifier = 'API%06x' % random.randrange(16**6)
            if 'comment' in downtime_data.keys():
                downtime_data['comment'] = "%s: %s" % (downtime_identifier, downtime_data['comment'])
            else:
                downtime_data['comment'] = "%s: no comment provided" % downtime_identifier
        except KeyError:
            raise BadRequestException('POST json data doesnt include a downtime key', status_code=400)
        # check if service or host is found in Livestatus
        if self.return_code == 200:
            # overwrite or create service_description key in downtime_data structure
            element_count = 0
            for downtime_element in self.data[ls_query_instance.entity]:
                if ls_query_instance.entity == 'hosts':
                    downtime_type = 'HOST'
                    downtime_data['host_name'] = downtime_element['display_name']
                elif ls_query_instance.entity == 'services':
                    downtime_type = 'SVC'
                    downtime_data['service_description'] = downtime_element['display_name']
                    downtime_data['host_name'] = downtime_element['host_display_name']
                else:
                    raise InternalProcessingException("downtimes can only be set on hosts or services", status_code=500)
                _ = ls_query_instance.create_downtime_query(downtime_type, downtime_data)
                ls_query_instance.query()
                element_count += 1
            return element_count, downtime_identifier
        else:
            return jsonify(self.data), self.return_code

    def delete_downtime(self, ls_query_instance):
        if "downtimes" not in self.data:
            raise InternalProcessingException("downtime not found", status_code=404)
        if self.return_code == 200:
            deleted_downtimes = []
            for downtime in self.data[self.entity]:
                if int(downtime["is_service"]) == 0:
                    downtime_type = 'HOST'
                else:
                    downtime_type = 'SVC'
                cmd = ls_query_instance.delete_downtime_query(downtime_type, downtime["id"])
                ls_query_instance.query()
                deleted_downtimes.append({
                    "id": int(downtime["id"]),
                    "command": cmd
                })
            return jsonify({"deleted downtimes": deleted_downtimes}), 200
        else:
            return jsonify(self.data), self.return_code

    def set_comment(self):
        pass

    def delete_comment(self):
        pass


class LivestatusActionCtx:
    def __init__(self, data, return_code):
        self.data = data
        self.return_code = return_code

    def __enter__(self):
        task_instance = LivestatusAction(self.data, self.return_code)
        return task_instance

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
