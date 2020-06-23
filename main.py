import os
import requests
import json
import time
import argparse
import logging
from pymongo import MongoClient
from bs4 import BeautifulSoup
from subprocess import call
from DB_Settings import *
from Settings import *

logging.basicConfig(
    format='%(asctime)s [%(levelname)s]: %(message)s',
    datefmt='%y-%m-%d %H:%M',
    level=logging.INFO
)

client = MongoClient(MONGODB_URL, MONGODB_PORT, retryWrites=False)
db = client[DB_NAME]
db.authenticate(DB_USER, DB_PASSWORD)
analyzed_collection = db[ANALYZED_COLLECTION]
etherscan_collection = db[ETHERSCAN_COLLECTION]
root_path = os.path.dirname(os.path.abspath(__file__))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--insert',dest='insert', help='insert contracts from Contract Library to DB', action='store_true')
    parser.add_argument('-p', '--page',dest='page', help='the page to insert to DB', type=int, default=1)
    parser.add_argument('-a', '--analyze',dest='analyze', help='analyze the contracts from DB', action='store_true')
    parser.add_argument('-f', '--fix',dest='fix', help='fix the DB', action='store_true')
    parser.add_argument('-g', '--getinfo',dest='getinfo', help='get the infomation', action='store_true')
    parser.add_argument('-t', '--infotype',dest='infotype', help='the information type')
    parser.add_argument('-u', '--unbounddetail',dest='unbounddetail', help='analyze unbound contracts', action='store_true')
    parser.add_argument('-adr', '--address',dest='address', help='the address need to analyze')
    parser.add_argument('-d', '--download',dest='download', help='the gas type contracts to be downloaded')

    args = parser.parse_args()

    if args.insert:
        contract_library(args.page)
    elif args.analyze:
        analyze()
    elif args.fix:
        fix()
    elif args.getinfo:
        if args.infotype in ['constant', 'bound', 'unbound']:
            get_info(args.infotype)
        else:
            logging.error('Please input -t [constant/bound/unbound]')
    elif args.unbounddetail:
        unbound_detail()
    elif args.address:
        analyze_address(args.address)
    elif args.download:
        download_contract(args.download)
    else:
        logging.error('Must use an argument. --help for the detail')

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

def contract_library(start: int):
    from selenium import webdriver
    base_url = 'https://contract-library.com/'
    count_exist = 0

    if OS_ENV == 'macos':
        driver = webdriver.Chrome('./chromedriver')
    else:
        driver = webdriver.Firefox(executable_path='./firefox-driver-linux')

    for page in range(start,1000):
        
        url = base_url + '?p=' + str(page)
        driver.get(url)
        time.sleep(3)
        table = driver.find_element_by_class_name('table-striped').find_element_by_tag_name('tbody')
        row = table.find_elements_by_tag_name('tr')
        for column in row:
            if count_exist > 20:
                driver.close()
                return

            addr = column.find_elements_by_tag_name('td')[0].text
            byte_code = get_bytecode_by_address(addr)
            existed = insert_new_contract_to_db(addr, byte_code)
            if existed:
                logging.info('P.%s %s: Exist' % (page, addr))
                count_exist += 1
            else:
                count_exist = 0
                logging.info('P.%s %s: Insert' % (page, addr))
    driver.close()

def insert_new_contract_to_db(address: str, bytecode: str) -> bool:
    contract = etherscan_collection.find_one({'_id': address})
    if not contract:
        new_item = {'_id': address, 'status': 'unchecked', 'bytecode': bytecode}
        resp = etherscan_collection.insert_one(new_item)
        return False
    else:
        return True

def analyze():
    contract = etherscan_collection.find_one({'status': 'unchecked'})
    while contract:
        address = contract['_id']
        new_item = {
            '_id': address,
            'bytecode': contract['bytecode']
        }
        if contract['bytecode']:
            print('+--------------------------------------------+')
            print('|', address, '|')
            print('+--------------------------------------------+')
            file_path = os.path.join(root_path, 'bytecode', '%s.hex' % address)
            with open(file_path, 'w') as f:
                f.write(contract['bytecode'])

            if OS_ENV == 'macos':
                call([PYTHON_FORMAT, '%s/main.py' % SMARTCONTRACTCFG_PATH, '-b', '-r', '-code', file_path, '-o', ANALYSIS_RESULT_PATH])
            else:
                call([PYTHON_FORMAT, '%s/main.py' % SMARTCONTRACTCFG_PATH, '-b', '-r', '-l', '-code', file_path, '-o', ANALYSIS_RESULT_PATH])
            
            insert_new = False
            if os.path.isfile('%s/%s/info.json' % (ANALYSIS_RESULT_PATH, address)):
                with open('%s/%s/info.json' % (ANALYSIS_RESULT_PATH, address), 'r') as f:
                    info = json.load(f)
                    gas_type = info['gas_type']
                    gas_formula = info['gas_formula']
                    max_gas = info['max_gas']
                    ins_num = info['ins_num']
                    node_num = info['node_num']
                    edge_num = info['edge_num']
                
                check_query = {'gas_type': gas_type, 'instruction_number': ins_num, 'node_number': node_num, 'edge_number': edge_num, 'max_gas': max_gas}
                contract = analyzed_collection.find_one(check_query)

                if contract:
                    info_message = 'Duplicate'
                    update_value = {'$set': {'status': 'duplicate', 'reference_contract': contract['_id']}}
                else:
                    madmax_warning = get_madmax_warning(address)
                    info_message = 'Insert'
                    insert_new = True
                    update_value = {'$set': {'status': 'checked'}}
                    new_item['status'] = 'checked'
                    new_item['gas_type'] = gas_type
                    new_item['gas_formula'] = gas_formula
                    new_item['max_gas'] = max_gas
                    new_item['instruction_number'] = ins_num
                    new_item['node_number'] = node_num
                    new_item['edge_number'] = edge_num
                    new_item['madmax_warning'] = madmax_warning
            else:
                info_message = 'Error'
                if os.path.isfile('%s/%s/error.txt' % (ANALYSIS_RESULT_PATH, address)):
                    with open('%s/%s/error.txt' % (ANALYSIS_RESULT_PATH, address), 'r') as f:
                        error = f.read()
                else:
                    error = None
                update_value = {'$set': {'status': 'error', 'error_message': error}}

            etherscan_collection.update_one({'_id': address}, update_value)
            if insert_new:
                analyzed_collection.insert_one(new_item)

            call(['rm', file_path])
        else:
            logging.info('No bytecode: %s' % address)
            update_value = {'$set': {'status': 'no_bytecode'}}
            etherscan_collection.update_one({'_id': address}, update_value)
        
        logging.info('Contract Status: %s\n' % info_message)
        contract = etherscan_collection.find_one({'status': 'unchecked'})

def analyze_address(address):
    contract = etherscan_collection.find_one({'_id': address})
    bytecode = contract['bytecode']
    print('+--------------------------------------------+')
    print('|', address, '|')
    print('+--------------------------------------------+')
    file_path = os.path.join(root_path, 'bytecode', '%s.hex' % address)
    with open(file_path, 'w') as f:
        f.write(contract['bytecode'])

    if OS_ENV == 'macos':
        call([PYTHON_FORMAT, '%s/main.py' % SMARTCONTRACTCFG_PATH, '-b', '-r', '-code', file_path, '-o', ANALYSIS_RESULT_PATH])
    else:
        call([PYTHON_FORMAT, '%s/main.py' % SMARTCONTRACTCFG_PATH, '-b', '-r', '-l', '-code', file_path, '-o', ANALYSIS_RESULT_PATH])

    insert_new = False
    new_item = {
        '_id': address,
        'bytecode': contract['bytecode']
    }
    if os.path.isfile('%s/%s/info.json' % (ANALYSIS_RESULT_PATH, address)):
        with open('%s/%s/info.json' % (ANALYSIS_RESULT_PATH, address), 'r') as f:
            info = json.load(f)
            gas_type = info['gas_type']
            gas_formula = info['gas_formula']
            max_gas = info['max_gas']
            ins_num = info['ins_num']
            node_num = info['node_num']
            edge_num = info['edge_num']
        
        check_query = {'gas_type': gas_type, 'instruction_number': ins_num, 'node_number': node_num, 'edge_number': edge_num, 'max_gas': max_gas}
        contract = analyzed_collection.find_one(check_query)

        if contract:
            info_message = 'Duplicate'
            update_value = {'$set': {'status': 'duplicate', 'reference_contract': contract['_id']}}
        else:
            madmax_warning = get_madmax_warning(address)
            info_message = 'Insert'
            insert_new = True
            update_value = {'$set': {'status': 'checked'}}
            new_item['status'] = 'checked'
            new_item['gas_type'] = gas_type
            new_item['gas_formula'] = gas_formula
            new_item['max_gas'] = max_gas
            new_item['instruction_number'] = ins_num
            new_item['node_number'] = node_num
            new_item['edge_number'] = edge_num
            new_item['madmax_warning'] = madmax_warning
    else:
        info_message = 'Error'
        if os.path.isfile('%s/%s/error.txt' % (ANALYSIS_RESULT_PATH, address)):
            with open('%s/%s/error.txt' % (ANALYSIS_RESULT_PATH, address), 'r') as f:
                error = f.read()
        else:
            error = None
        update_value = {'$set': {'status': 'error', 'error_message': error}}

    etherscan_collection.update_one({'_id': address}, update_value)
    if insert_new:
        analyzed_collection.insert_one(new_item)

    call(['rm', file_path])

def get_madmax_warning(address):
    from selenium import webdriver
    from selenium.common.exceptions import NoSuchElementException

    if OS_ENV == 'macos':
        driver = webdriver.Chrome('./chromedriver')
    else:
        driver = webdriver.Firefox(executable_path='./firefox-driver-linux')
    url = 'https://contract-library.com/contracts/Ethereum/' + address
    driver.get(url)
    time.sleep(2)
    warning_list = list()
    items = driver.find_elements_by_class_name('warning-name')
    if len(items) > 0:
        for item in items:
            warning_list.append(item.text)
        logging.info('%s [%s] Warning: %s' % (address, gas_type, ', '.join(warning_list)))
    else:
        logging.info('%s [%s] No Warning' % (address, gas_type))
    driver.close()
    return warning_list

def get_info(contract_type):
    contract_list = analyzed_collection.find({'gas_type': contract_type}, no_cursor_timeout=True)
    count = 0
    gas_min = 10000
    gas_max = 0
    gas_sum = 0
    if contract_type != 'unbound':
        for contract in contract_list:
            gas = int(contract['max_gas'])
            if gas < 10000000:
                gas_max = gas if gas > gas_max else gas_max
                gas_min = gas if gas < gas_min and gas > 0 else gas_min
                gas_sum += gas
                count += 1
                if count % 50 == 0:
                    print(count)
            else:
                logging.warning('Gas Over Bound: %s - %s' % (contract['_id'], gas))
    else:
        for contract in contract_list:
            count += 1
    contract_list.close()
    logging.info('#Contract: %s' % count)
    if contract_type != 'unbound':
        logging.info('Max gas: %s' % gas_max)
        logging.info('Min gas: %s' % gas_min)
        logging.info('Average gas: %s' % (gas_sum/count))

def unbound_detail():
    from selenium import webdriver
    from selenium.common.exceptions import NoSuchElementException

    if OS_ENV == 'macos':
        driver = webdriver.Chrome('./chromedriver')
    else:
        driver = webdriver.Firefox(executable_path='./firefox-driver-linux')

    contract_list = analyzed_collection.find({'gas_type': 'unbound'}, no_cursor_timeout=True)
    count = 0
    for contract in contract_list:
        count += 1
        address = contract['_id']
        gas_type = contract['gas_type']
        url = 'https://contract-library.com/contracts/Ethereum/' + address
        driver.get(url)
        time.sleep(2)
        warning_list = list()
        items = driver.find_elements_by_class_name('warning-name')
        if len(items) > 0:
            for item in items:
                warning_list.append(item.text)
            logging.info('%s [%s] Warning: %s' % (address, gas_type, ', '.join(warning_list)))
        else:
            logging.info('%s [%s] No Warning' % (address, gas_type))
        if warning_list:
            update_value = {'$set': {'madmax_warning': warning_list}}
        else:
            update_value = {'$set': {'madmax_warning': None}}
        analyzed_collection.update_one({'_id': address}, update_value)
    print(count)
    driver.close()

def fix():
    query = {'status': 'error'}
    contract_list = etherscan_collection.find(query, no_cursor_timeout=True)
    for contract in contract_list:
        address = contract['_id']
        bytecode = contract['bytecode']
        if bytecode == '0x':
            etherscan_collection.update_one({'_id': address}, {
                '$set': {
                    'status': 'empty'
                }
            })
            analyzed_collection.delete_one({'_id': address})
            logging.info('%s update' % address)
        else:
            logging.info('%s error' % address)

def download_contract(contract_type):
    directory = '/Users/Harrison/Desktop/Etherscan-%s' % contract_type
    if not os.path.exists(directory):
        os.mkdir(directory)
    contract_list = analyzed_collection.find({'gas_type': contract_type}, no_cursor_timeout=True)
    for contract in contract_list:
        with open('%s/%s.hex' % (directory, contract['_id']), 'w') as f:
            f.write(contract['bytecode'])

if __name__ == '__main__':
    main()