# #####################################################################################
# Copyright (c) 2021-23, VMware Inc, and the Certifier Authors.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ##############################################################################
"""
Basic pytests to exercise stripped-down Client-Server SSL Socket
communication using mTLS.

# pylint: disable=line-too-long

Sample test program built based on these references:

https://stackoverflow.com/questions/44343230/mutual-ssl-authentication-in-simple-echo-client-server-python-sockets-ssl-m
https://discuss.python.org/t/ssl-certificate-verify-failed-certificate-verify-failed-ip-address-mismatch-certificate-is-not-valid-for-xxx-xxx-x-xx-ssl-c-997/28403/4

leads to: https://stackoverflow.com/questions/52855924/problems-using-paho-mqtt-client-with-python-3-7
  where the suggestion to use --addext 'subjectAltName=IP:127.0.0.1' has been provided.

Ref: https://gist.github.com/fntlnz/cf14feb5a46b2eda428e000157447309
  for a good discussion of how-to generate root-certificate and server key/certificates

Ref: https://stackoverflow.com/questions/30700348/how-to-validate-verify-an-x509-certificate-chain-of-trust-in-python
  After generating server-and client's public certificate using a common CA root key,
  both sides have to "validate" the certificate chain. Check if this is done by SSL
  Python interfaces, automatically.

So, finally, generate client / server certificates and private-keys using these commands:
$ openssl req -new -x509 -days 365 -noenc -out client.pem -keyout client.key --addext 'subjectAltName=IP:127.0.0.1'
$ openssl req -new -x509 -days 365 -nodes -out server.pem -keyout server.key --addext 'subjectAltName=IP:127.0.0.1'

Other useful references to understand Certificate chains and domain knowledge:
 - https://shagihan.medium.com/what-is-certificate-chain-and-how-to-verify-them-be429a030887
 - https://stackoverflow.com/questions/30700348/how-to-validate-verify-an-x509-certificate-chain-of-trust-in-python
 - https://pythontic.com/ssl/sslcontext/load_verify_locations - Good simple SSL connection example
 - https://rob-blackbourn.medium.com/secure-communication-with-python-ssl-certificate-and-asyncio-939ae53ccd35
 - https://gist.github.com/fntlnz/cf14feb5a46b2eda428e000157447309#create-root-key

"""
import os
import socket
import ssl
import pprint
# pylint: disable-next=line-too-long
from OpenSSL.crypto import X509Store, X509StoreContext, load_certificate, FILETYPE_PEM, X509StoreContextError

# pylint: enable=line-too-long

# Resolves to current tests/pytests dir
THIS_SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

SERVER_HOST = '127.0.0.1'
SERVER_PORT = 1234

# These certificate *.pem and private-key *.key files are generated by
# the openssl utility.
SERVER_SELF_SIGNED_CERT = THIS_SCRIPT_DIR + '/data/server.public-cert.pem'
SERVER_SELF_SIGNED_KEYF = THIS_SCRIPT_DIR + '/data/server-private.key'
CLIENT_SELF_SIGNED_CERT = THIS_SCRIPT_DIR + '/data/client.public-cert.pem'
CLIENT_SELF_SIGNED_KEYF = THIS_SCRIPT_DIR + '/data/client-private.key'

# The openssl utility is invoked to specify few fields, where the
# 'commonName' field is the 3rd field specified; Hence, offset=2
# This hard-coded field-number arises from the way the openssl req
# command is run in gen_client_server_certs_key_files.sh
COMMON_NAME_FIELD = 2

ROOT_POLICY_CERT        = THIS_SCRIPT_DIR + '/data/rootCA.cert'
WRONG_ROOT_POLICY_CERT  = THIS_SCRIPT_DIR + '/data/wrong-rootCA.cert'
SERVER_ROOT_SIGNED_CERT = THIS_SCRIPT_DIR + '/data/server-mydomain.com.cert'
SERVER_ROOT_SIGNED_KEYF = THIS_SCRIPT_DIR + '/data/server-mydomain.com.key'
CLIENT_ROOT_SIGNED_CERT = THIS_SCRIPT_DIR + '/data/client-mydomain.com.cert'
CLIENT_ROOT_SIGNED_KEYF = THIS_SCRIPT_DIR + '/data/client-mydomain.com.key'

# ##############################################################################
# To see output, run: pytest --capture=tee-sys -v
def test_server_process_with_mtls_self_signed_cert():
    """
    Run server-process that listens on an end-point on a secure SSL channel.
    This exercises server process using a self-signed cert.
    """
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(certfile=SERVER_SELF_SIGNED_CERT, keyfile=SERVER_SELF_SIGNED_KEYF)
    context.load_verify_locations(cafile=CLIENT_SELF_SIGNED_CERT)

    bindsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    bindsocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    bindsocket.bind((SERVER_HOST, SERVER_PORT))
    bindsocket.listen(10)
    print('\nWaiting for client ...')

    new_socket, fromaddr = bindsocket.accept()
    print('\nClient connected: ', fromaddr[0], ":", fromaddr[1])

    secure_sock = context.wrap_socket(new_socket, server_side=True)

    print('\ngetpeername:', repr(secure_sock.getpeername()))
    print('\nsecure socket cipher(): ', secure_sock.cipher())
    print('\nPretty-print get peer Certificate:\n', pprint.pformat(secure_sock.getpeercert()))
    cert = secure_sock.getpeercert()
    print('\nPeer Certificate:', cert)

    # Verify that client certificate was created as expected by the
    # setup script,gen_client_server_certs_key_files.sh
    if not cert or ('commonName', 'test') not in cert['subject'][COMMON_NAME_FIELD]:
        raise Exception("ERROR")

    try:
        data = secure_sock.recv(1024)
        print('\nReceived from client: ', str(data, 'UTF-8'))

        ret_hdr = 'Return back to client: '
        print('\nReturn message back to client:', ret_hdr + str(data, 'UTF-8'))
        secure_sock.write(bytes(ret_hdr, 'UTF-8') +  data)
    finally:
        secure_sock.close()
        bindsocket.close()

# ##############################################################################
# To see output, run: pytest --capture=tee-sys -v
def test_client_app_with_mtls_self_signed_cert():
    """
    Run client-application that sends message via secure SSL channel.
    This exercises a client process talking to a server using a self-signed cert.
    """
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(certfile=CLIENT_SELF_SIGNED_CERT, keyfile=CLIENT_SELF_SIGNED_KEYF)
    context.load_verify_locations(cafile=SERVER_SELF_SIGNED_CERT)

    bindsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    bindsocket.setblocking(1)
    bindsocket.connect((SERVER_HOST, SERVER_PORT))

    if ssl.HAS_SNI:
        secure_sock = context.wrap_socket(bindsocket, server_side=False,
                                          server_hostname=SERVER_HOST)
    else:
        secure_sock = context.wrap_socket(bindsocket, server_side=False)

    cert = secure_sock.getpeercert()
    print('\n\nPretty-print getpeercert() returned Certificate:\n', pprint.pformat(cert))
    print(cert['subject'][COMMON_NAME_FIELD])

    # Verify that server certificate was created as expected by the
    # setup script,gen_client_server_certs_key_files.sh
    if not cert or ('commonName', 'test') not in cert['subject'][COMMON_NAME_FIELD]:
        raise Exception("ERROR")

    send_msg = 'hello'
    try:
        secure_sock.send(bytes(send_msg, 'UTF-8'))

        recv_data = secure_sock.recv(1024)
        recv_data_str = str(recv_data, 'UTF-8')

        print('\nReceived message from server:', recv_data_str)

        # Server should have prepended this to our message and returned it
        assert recv_data_str == 'Return back to client: ' + send_msg
    finally:
        secure_sock.close()
        bindsocket.close()

# ##############################################################################
def test_verify_certs_versus_root_cert():
    """
    Validate that the server / client certificates correctly verify v/s a valid
    root CA certificate, and correctly fail validation v/s an wrong root CA cert.
    """
    result = verify_cert_file_vs_root_cert_file(ca_root_cert_location = ROOT_POLICY_CERT,
                                                cert_location = SERVER_ROOT_SIGNED_CERT)
    assert result is True

    result = verify_cert_file_vs_root_cert_file(ca_root_cert_location = ROOT_POLICY_CERT,
                                                cert_location = CLIENT_ROOT_SIGNED_CERT)
    assert result is True

    result = verify_cert_file_vs_root_cert_file(ca_root_cert_location = WRONG_ROOT_POLICY_CERT,
                                                cert_location = SERVER_ROOT_SIGNED_CERT)
    assert result is False

    result = verify_cert_file_vs_root_cert_file(ca_root_cert_location = WRONG_ROOT_POLICY_CERT,
                                                cert_location = CLIENT_ROOT_SIGNED_CERT)
    assert result is False

# ##############################################################################
# To see output, run: pytest --capture=tee-sys -v
def test_server_process_with_mtls_root_signed_cert():
    """
    Run server-process that listens on an end-point on a secure SSL channel.
    This exercises server process using a cert signed by a root CA.
    """
    # Server needs to authenticate the client; hence 'Purpose.CLIENT_AUTH'
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(certfile=SERVER_ROOT_SIGNED_CERT, keyfile=SERVER_ROOT_SIGNED_KEYF)
    context.load_verify_locations(cafile=ROOT_POLICY_CERT)

    bindsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    bindsocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    bindsocket.bind((SERVER_HOST, SERVER_PORT))
    bindsocket.listen(10)
    print('\nWaiting for client ...')

    new_socket, fromaddr = bindsocket.accept()
    print('\nClient connected: ', fromaddr[0], ":", fromaddr[1])

    secure_sock = context.wrap_socket(new_socket, server_side=True)

    print('\ngetpeername:', repr(secure_sock.getpeername()))
    print('\nsecure socket cipher(): ', secure_sock.cipher())

    peer_cert = secure_sock.getpeercert()
    print('\nPretty-print client peer Certificate:\n', pprint.pformat(peer_cert))

    peer_pem_cert = ssl.DER_cert_to_PEM_cert(secure_sock.getpeercert(True))
    peer_x509_cert = load_certificate(FILETYPE_PEM, peer_pem_cert.encode())
    with open(ROOT_POLICY_CERT, encoding='utf-8') as root_cert_file:
        root_x509_cert = load_certificate(FILETYPE_PEM, root_cert_file.read())

    # Verify that client certificate was signed by root CA
    if verify_certificate_vs_root_cert(ca_root_cert = root_x509_cert,
                                       untrusted_cert = peer_x509_cert) is False:
        raise Exception('Error: Client cert failed verification v/s root-cert')
    try:
        data = secure_sock.recv(1024)
        print('\nReceived from client: ', str(data, 'UTF-8'))

        ret_hdr = 'Return back to client: '
        print('\nReturn message back to client:', ret_hdr + str(data, 'UTF-8'))
        secure_sock.write(bytes(ret_hdr, 'UTF-8') +  data)
    finally:
        secure_sock.close()
        bindsocket.close()

# ##############################################################################
# To see output, run: pytest --capture=tee-sys -v
def test_client_app_with_mtls_root_signed_cert():
    """
    Run client-application that sends message via secure SSL channel.
    This exercises a client process talking to a server whose cert
    was generated and signed by a root CA.
    """
    # Client needs to authenticate the server; hence 'Purpose.SERVER_AUTH'
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(certfile=CLIENT_ROOT_SIGNED_CERT, keyfile=CLIENT_ROOT_SIGNED_KEYF)
    context.load_verify_locations(cafile=ROOT_POLICY_CERT)

    bindsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    bindsocket.setblocking(1)
    bindsocket.connect((SERVER_HOST, SERVER_PORT))

    if ssl.HAS_SNI:
        secure_sock = context.wrap_socket(bindsocket, server_side=False,
                                          server_hostname=SERVER_HOST)
    else:
        secure_sock = context.wrap_socket(bindsocket, server_side=False)

    peer_cert = secure_sock.getpeercert()
    print('\n\nPretty-print server peer Certificate:\n', pprint.pformat(peer_cert))
    peer_pem_cert = ssl.DER_cert_to_PEM_cert(secure_sock.getpeercert(True))
    peer_x509_cert = load_certificate(FILETYPE_PEM, peer_pem_cert.encode())
    with open(ROOT_POLICY_CERT, encoding='utf-8') as root_cert_file:
        root_x509_cert = load_certificate(FILETYPE_PEM, root_cert_file.read())

    # Verify that server certificate was signed by root CA
    if verify_certificate_vs_root_cert(ca_root_cert = root_x509_cert,
                                       untrusted_cert = peer_x509_cert) is False:
        raise Exception('Error: Server cert failed verification v/s root-cert')

    send_msg = 'hello'
    try:
        secure_sock.send(bytes(send_msg, 'UTF-8'))

        recv_data = secure_sock.recv(1024)
        recv_data_str = str(recv_data, 'UTF-8')

        print('\nReceived message from server:', recv_data_str)

        # Server should have prepended this to our message and returned it
        assert recv_data_str == 'Return back to client: ' + send_msg
    finally:
        secure_sock.close()
        bindsocket.close()

# ##############################################################################
# Helper methods:
# ##############################################################################

# pylint: disable-next=line-too-long
# Ref: https://stackoverflow.com/questions/30700348/how-to-validate-verify-an-x509-certificate-chain-of-trust-in-python
def verify_cert_file_vs_root_cert_file(ca_root_cert_location, cert_location):
    """
    Helper method to validate that a certificate being examined is valid
    w.r.t. the root CA certificate provided. (The certificate read from
    input 'cert_location' should have been signed by the root CA at the
    'ca_root_cert_location' file.)
    """
    with open(ca_root_cert_location, encoding='utf-8') as root_cert_file:
        root_cert = load_certificate(FILETYPE_PEM, root_cert_file.read())

    with open(cert_location, encoding='utf-8') as cert_file:
        untrusted_cert = load_certificate(FILETYPE_PEM, cert_file.read())

    return verify_certificate_vs_root_cert(root_cert, untrusted_cert)

# ##############################################################################
def verify_certificate_vs_root_cert(ca_root_cert, untrusted_cert):
    """
    Verify untrusted cert v/s root certificate, both of which are expected
    to be X509 format.
    """
    store = X509Store()
    store.add_cert(ca_root_cert)
    store_ctx = X509StoreContext(store, untrusted_cert)

    try:
        if store_ctx.verify_certificate() is None:
            return True
    except X509StoreContextError as error:
        print('\nstore_ctx.verify_certificate() raise an exception for untrusted cert:', error)
        return False
    return False

# ##############################################################################
# Based on example 12 from:
# https://python.hotexamples.com/examples/ssl/SSLContext/load_verify_locations/python-sslcontext-load_verify_locations-method-examples.html
#
def verify_certificate_vs_root_cert0(ca_root_cert_location, cert_location, key_location):
    """Attempted version -- did not work ..."""
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_verify_locations(ca_root_cert_location)
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    ssl_context.load_cert_chain(certfile=cert_location, keyfile=key_location)

    return ssl_context

def verify_certificate_vs_root_cert2(ca_root_cert_location, cert_location, key_location):
    """Attempted version -- did not work ..."""

    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH,
                                             cafile = ca_root_cert_location)

    # ssl_context.load_verify_locations(cafile=ca_root_cert_location)
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    ssl_context.load_cert_chain(certfile=cert_location, keyfile=key_location)
    # if ssl_context.validate_certificate(cert_location):
    #     return ssl_context
    # else:
    #     return None
    return ssl_context