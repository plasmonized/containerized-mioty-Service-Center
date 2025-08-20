# mioty_BSSCI
This is a basic implementation of the mioty BSSCI protocol. It can be used with every mioty basestation following the mioty BSSCI v1.0.0.0 standard. Default the received messages will be published in the specified mqtt broker under the topic "bssci/"

## Usage
1. Setup endpoint  
Change or add endpoints to the endpoint.json according to the two sample endpoints. Endpoints can be added through MQTT at runtime. 
2. Create certificates  
For the TLS connection between the basestation and the SC we need certificates. The necessary certificates can be creates with the following commands:
    ``` 
    # 1. Create CA-key and CA-certificate
    openssl genrsa -out ca_key.pem 4096
    openssl req -x509 -new -key ca_key.pem -sha256 -days 3650 -out ca_cert.pem

    # 2. Create server-key and CSR 
    openssl genrsa -out service_center_key.pem 2048
    openssl req -new -key service_center_key.pem -out service_center.csr

    # 3. Sign server-certificate with CA
    openssl x509 -req -in service_center.csr \
    -CA ca_cert.pem -CAkey ca_key.pem -CAcreateserial \
    -out service_center_cert.pem -days 825 -sha256
    ```

3. Setup environment varibales 
Change the varibales in the "bssci_config.py" according to your individual setup. 

4. Start the service center  
Enter 
    > python main.py

5. Setup the basestation  
Setup the ip, port and certificates in the basestation. 

6. Data  
Data is then published under the individual topic for each endpoint and looks something like this: 
> bssci/ep/{eui}/ul  
{"bs_eui": "70b3d59cd0000022", "rxTime": 1755708639613188798, "snr": 22.882068634033203, "rssi": -71.39128875732422, "cnt": 4830, "data": [2, 83, 1, 97, 6, 34, 3, 30, 2, 121, 3, 57, 12, 100, 24, 51, 10, 93, 5, 45, 5]}


## Advanced Usage 
### Setting up endpoints at runtime
To add endpoints at runtime create a topic under the base topic like the following 
>{BASE_TOPIC}/ep/{eui}/config  

The BASE_TOPIC is specified in the bssci_config.py. 
The eui is individual for each endpoint and is delivered by the endpoint manufacturer.  
The payload for the topic looks like 
> {"nwKey": "0011223344556677889AABBCCDDEEFF", "shortAddr": "0000", "bidi": false}

and the content also needs to be deliverd by the endpoint manufacturer. 

### Basestation status
The service center publishes periodically the status of the basestation. This status can be seen in the topic
>{BASE_TOPIC}/bs/{bs_eui}
The basestation eui (bs_eui) is individual for each basestation.

and looks something like this
>  {"code": 0, "memLoad": 0.3347685933113098, "cpuLoad": 0.23333333432674408, "dutyCycle": 0.0, "time": 1755706414392137804, "uptime": 1566}


