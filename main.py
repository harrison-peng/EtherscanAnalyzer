import os
import requests
import json
import time
from pymongo import MongoClient
from bs4 import BeautifulSoup
from subprocess import call
from DB_Settings import *

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
        print('FIND CODE')
        print(code)
        if code not in sourcecode_list:
            sourcecode_list.append(code)
            with open('./bytecode_2/%s.hex' % address, 'w') as f:
                f.write(code.text)
    else:
        code = soup.find('pre', attrs={'class': 'wordwrap'})
        print('NOT FIND CODE')
        print(code)
        if code not in bytecode_list:
            sourcecode_list.append(code)
            with open('./bytecode/%s.hex' % address, 'w') as f:
                f.write(code.text)

def contract_library():
    from selenium import webdriver
    address = list()
    base_url = 'https://contract-library.com/?w=DoS%20(Unbounded%20Operation)'

    for page in range(50):
        driver = webdriver.Chrome('./chromedriver')
        url = base_url + '&p=' + str(page+1)
        driver.get(url)
        time.sleep(3)
        table = driver.find_element_by_class_name('table-striped').find_element_by_tag_name('tbody')
        row = table.find_elements_by_tag_name('tr')
        for column in row:
            addr = column.find_elements_by_tag_name('td')[0].text
            print(addr)
            get_bytecode_by_address(addr)
            address.append(addr)
        driver.close()

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
    print('Start')
    root_path = os.path.dirname(os.path.abspath(__file__))
    check_list = collection.find()
    for item in check_list:
        print(item)
        address = item['_id']
        check = item['check']
        if check == 'unchecked':
            print(address)
            file_path = os.path.join(root_path, 'bytecode', '%s.hex' % address)
            with open(file_path, 'w') as f:
                f.write(item['bytecode'])

            call(['python', '/Users/Harrison/Documents/Research/SmartContractCFG/main.py', '-b', '-r', '-code', file_path, '-o', '/Users/Harrison/Desktop/contract-library'])
            
            if os.path.isfile('/Users/Harrison/Desktop/contract-library/%s/gas_type.txt' % address):
                with open('/Users/Harrison/Desktop/contract-library/%s/gas_type.txt' % address, 'r') as f:
                    gas_type = f.read()
                update_value = {'$set': {'check': 'checked', 'gas_type': gas_type}}
            else:
                update_value = {'$set': {'check': 'error'}}

            collection.update({'_id': address}, update_value)

            call(['rm', file_path])


if __name__ == '__main__':
	# contract_library()
    # insert_check_list()
    analyze()