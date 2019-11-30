import os
import requests
import json
from bs4 import BeautifulSoup
from subprocess import call

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
    url = 'https://etherscan.io/address/%s#code' % address
    user_agent = {'User-agent': 'Mozilla/5.0'}
    html = requests.get(url, headers=user_agent)
    soup = BeautifulSoup(html.content, 'html.parser')
    code = soup.find('pre', attrs={'id': 'editor'})
    sourcecode_list = list()
    bytecode_list = list()
    if code:
        if code not in sourcecode_list:
            sourcecode_list.append(code)
            with open('./sourcecode/%s.sol' % address, 'w') as f:
                f.write(code.text)
    else:
        code = soup.find('pre', attrs={'class': 'wordwrap'})
        if code not in bytecode_list:
            sourcecode_list.append(code)
            with open('./bytecode/%s.hex' % address, 'w') as f:
                f.write(code.text)

def contract_library():
    from selenium import webdriver
    address = list()
    base_url = 'https://contract-library.com/?w=DoS%20(Unbounded%20Operation)'

    for page in range(20):
        driver = webdriver.Chrome('./chromedriver')
        url = base_url + '&p=' + str(page+1)
        driver.get(url)
        table = driver.find_element_by_class_name('table-striped').find_element_by_tag_name('tbody')
        row = table.find_elements_by_tag_name('tr')
        for column in row:
            addr = column.find_elements_by_tag_name('td')[0].text
            print(addr)
            get_bytecode_by_address(addr)
            address.append(addr)
        driver.close()

def create_check_list():
    check_list = dict()
    root_path = os.path.dirname(os.path.abspath(__file__))
    for file_name in os.listdir(os.path.join(root_path, 'bytecode')):
        check_list[file_name] = False
    with  open('./bytecode_check_list.json', 'w') as f:
        f.write(json.dumps(check_list))

def analyze():
    with open('./bytecode_check_list.json', 'r') as f:
        check_list = json.loads(f.read())

    root_path = os.path.dirname(os.path.abspath(__file__))
    for file_name in os.listdir(os.path.join(root_path, 'bytecode')):
        if not check_list[file_name]:
            abs_path = os.path.join(root_path, 'bytecode', file_name)
            call(['python', '/Users/Harrison/Documents/Research/SmartContractCFG/main.py', '-b', '-r', '-code', abs_path, '-o', '/Users/Harrison/Desktop/contract-library'])
            check_list[file_name] = True
            with  open('./bytecode_check_list.json', 'w') as f:
                f.write(json.dumps(check_list))


if __name__ == '__main__':
	# contract_library()
    analyze()