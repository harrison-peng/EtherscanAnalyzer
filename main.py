import os
import requests
import json
import time
from pymongo import MongoClient
from bs4 import BeautifulSoup
from subprocess import call
from DB_Settings import *
from Settings import *

client = MongoClient(MONGODB_URL, MONGODB_PORT, retryWrites=False)
db = client[DB_NAME]
db.authenticate(DB_USER, DB_PASSWORD)
collection = db[COLLECTION_NAME]

def etherscan():
    base_url = 'https://etherscan.io'
    contracts_verified_url = base_url + '/contractsVerified/'
    contracts_address_base_url = base_url + '/address/'
    user_agent = {'User-agent': 'Mozilla/5.0'}
    
    for page in range(1):
        contracts_verified_address_url = contracts_verified_url + str(page+1)
        print(contracts_verified_address_url)
        html = requests.get(contracts_verified_address_url, headers=user_agent)
        soup = BeautifulSoup(html.content, 'html.parser')
        for item in soup.find('table', attrs={'class':'table-hover'}).find_all('tr'):
            address = item.find('a').text
            contracts_address_url = contracts_address_base_url + address
            html = requests.get(contracts_address_url, headers=user_agent)
            address_soup = BeautifulSoup(html.content, 'html.parser')
            contract = address_soup.find(class_='js-sourcecopyarea')
            if contract and address != '':
                with open('contracts/%s.sol' % address, 'w') as f:
                    f.write(contract.text)

def get_bytecode_by_address(address):
    sourcecode_list = list()
    bytecode_list = list()
    url = 'https://etherscan.io/address/%s#code' % address
    user_agent = {'User-agent': 'Mozilla/5.0'}
    html = requests.get(url, headers=user_agent)
    time.sleep(1)
    soup = BeautifulSoup(html.content, 'html.parser')
    time.sleep(1)
    code = soup.find('div', attrs={'id': 'verifiedbytecode2'})
    if code:
        if code not in sourcecode_list:
            sourcecode_list.append(code)
            bytecode = code.text
    else:
        code = soup.find('pre', attrs={'class': 'wordwrap'})
        if code not in bytecode_list:
            sourcecode_list.append(code)
            bytecode = code.text
    return bytecode

def contract_library():
    from selenium import webdriver
    # address = list()
    base_url = 'https://contract-library.com/'

    for page in range(50,100):
        driver = webdriver.Chrome('./chromedriver')
        url = base_url + '?p=' + str(page+1)
        driver.get(url)
        time.sleep(3)
        table = driver.find_element_by_class_name('table-striped').find_element_by_tag_name('tbody')
        row = table.find_elements_by_tag_name('tr')
        for column in row:
            addr = column.find_elements_by_tag_name('td')[0].text
            print(addr)
            byte_code = get_bytecode_by_address(addr)
            insert_new_contract_to_db(addr, byte_code)
            # address.append(addr)
        driver.close()

def insert_new_contract_to_db(address, bytecode):
    contract = collection.find_one({'_id': address})
    if not contract:
        print('Insert')
        new_item = {'_id': address, 'status': 'unchecked', 'gas_type': None, 'error': None, 'bytecode': bytecode}
        resp = collection.insert_one(new_item)
    else:
        print('Exist')

def insert_check_list():
    root_path = os.path.dirname(os.path.abspath(__file__))
    for file_name in os.listdir(os.path.join(root_path, 'bytecode')):
        address = file_name.split('.')[0]
        contract = collection.find_one({'_id': address})
        print('address:', address)
        
        with open(os.path.join(root_path, 'bytecode/%s' % file_name), 'r') as f:
            bytecode = f.read()
        print(bytecode)
        if contract:
            update_item = {'$set': {'bytecode': bytecode}}
            resp = collection.update({'_id': address}, update_item)
        else:
            new_item = {'_id': address, 'check': 'unchecked', 'gas_type': '', 'bytecode': bytecode}
            resp = collection.insert(new_item)

def analyze():
    root_path = os.path.dirname(os.path.abspath(__file__))
    contract = collection.find_one({'status': 'unchecked'})
    while contract:
        address = contract['_id']
        if contract['bytecode']:
            check = contract['status']
            print(address)
            file_path = os.path.join(root_path, 'bytecode', '%s.hex' % address)
            with open(file_path, 'w') as f:
                f.write(contract['bytecode'])

            call(['python', '%s/main.py' % SMARTCONTRACTCFG_PATH, '-b', '-r', '-code', file_path, '-o', ANALYSIS_RESULT_PATH])
            
            if os.path.isfile('%s/%s/gas_type.txt' % (ANALYSIS_RESULT_PATH, address)):
                with open('%s/%s/gas_type.txt' % (ANALYSIS_RESULT_PATH, address), 'r') as f:
                    results = f.readlines()
                    gas_type = results[0].strip()
                    max_gas = results[1].strip()
                    ins_num = results[2].strip()
                    node_num = results[3].strip()
                    edge_num = results[4].strip()

                update_value = {'$set': {'status': 'checked_1', 'gas_type': gas_type, 'max_gas': max_gas, 'instruction_number': ins_num, 'node_number': node_num, 'edge_number': edge_num}}
            elif os.path.isfile('%s/%s/error.txt' % (ANALYSIS_RESULT_PATH, address)):
                with open('%s/%s/error.txt' % (ANALYSIS_RESULT_PATH, address), 'r') as f:
                    error = f.read()
                update_value = {'$set': {'status': 'error', 'gas_type': '', 'max_gas': '', 'instruction_number': '', 'node_number': '', 'edge_number': '', 'error': error}}
            else:
                update_value = {'$set': {'status': 'error', 'gas_type': '', 'max_gas': '', 'instruction_number': '', 'node_number': '', 'edge_number': '', 'error': None}}

            collection.update_one({'_id': address}, update_value)

            call(['rm', file_path])
        else:
            print('No bytecode: %s' % address)
            update_value = {'$set': {'status': 'no_bytecode'}}
            collection.update_one({'_id': address}, update_value)
        
        contract = collection.find_one({'status': 'unchecked'})

def fix_db():
    contract = collection.find_one({'status': 'loop_error'})
    while contract:
        address = contract['_id']
        update_value = {'$set': {'status': 'unchecked', 'error': None}}
        collection.update_one({'_id': address}, update_value)
        print(address)
        contract = collection.find_one({'status': 'loop_error'})

if __name__ == '__main__':
	# contract_library()
    analyze()
    # fix_db()