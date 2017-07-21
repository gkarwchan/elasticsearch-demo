from __future__ import print_function

import json
import re
import boto3
from elasticsearch import Elasticsearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

print('Loading function')


def lambda_handler(event, context):
    #print("Received event: " + json.dumps(event, indent=2))
    
    session = boto3.session.Session()
    credentials = session.get_credentials()

    # Get proper credentials for ES auth
    awsauth = AWS4Auth(credentials.access_key,
                       credentials.secret_key,
                       session.region_name, 'es',
                       session_token=credentials.token)
                       
    # Connect to ES
    es = Elasticsearch(
        "https://search-contacts-roa7awyjn3ddfpw2nxkwsqitja.us-east-1.es.amazonaws.com",
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )
    
    print("Cluster info:")
    print(es.info())
                       
    for record in event['Records']:
        print("New Record to process:")
        #print(record['eventID'])
        #print(record['eventName'])
        insert_document(es, record)
        #print("DynamoDB Record: " + json.dumps(record['dynamodb'], indent=2))
        
    return 'Successfully processed {} records.'.format(len(event['Records']))


# Process INSERT events
def insert_document(es, record):
    table = getTable(record)
    print("Dynamo Table: " + table)
    
    # Create index if missing
    if es.indices.exists(table) == False:
        print("Create missing index: " + table)
        
        es.indices.create(table,
                          body='{"settings": { "index.mapping.coerce": true } }')
        
        print("Index created: " + table)

    # Unmarshal the DynamoDB JSON to a normal JSON
    doc = json.dumps(unmarshalJson(record['dynamodb']['NewImage']))
    
    print("New document to Index:")
    print(doc)

    newId = generateId(record)
    es.index(index=table,
             body=doc,
             id=newId,
             doc_type=table,
             refresh=True)
            
    print("Success - New Index ID: " + newId)

def getTable(record):
    p = re.compile('arn:aws:dynamodb:.*?:.*?:table/([0-9a-zA-Z_-]+)/.+')
    m = p.match(record['eventSourceARN'])
    if m is None:
        raise Exception("Table not found in SourceARN")
    return m.group(1).lower()
    
# Generate the ID for ES. Used for deleting or updating item later
def generateId(record):
    keys = unmarshalJson(record['dynamodb']['Keys'])
    
    # Concat HASH and RANGE key with | in between
    newId = ""
    i = 0
    for key, value in keys.items():
        if (i > 0):
            newId += "|"
        newId += str(value)
        i += 1
        
    return newId

# Unmarshal a JSON that is DynamoDB formatted
def unmarshalJson(node):
    data = {}
    data["M"] = node
    return unmarshalValue(data, True)

# ForceNum will force float or Integer to 
def unmarshalValue(node, forceNum=False):
    for key, value in node.items():
        if (key == "NULL"):
            return None
        if (key == "S" or key == "BOOL"):
            return value
        if (key == "N"):
            if (forceNum):
                return int_or_float(value)
            return value
        if (key == "M"):
            data = {}
            for key1, value1 in value.items():
                data[key1] = unmarshalValue(value1, True)
            return data
        if (key == "BS" or key == "L"):
            data = []
            for item in value:
                data.append(unmarshalValue(item))
            return data
        if (key == "SS"):
            data = []
            for item in value:
                data.append(item)
            return data
        if (key == "NS"):
            data = []
            for item in value:
                if (forceNum):
                    data.append(int_or_float(item))
                else:
                    data.append(item)
            return data

# Detect number type and return the correct one
def int_or_float(s):
    try:
        return int(s)
    except ValueError:
        return float(s)