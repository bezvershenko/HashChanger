import pymorphy2
import vk
import pymongo
import requests

from flask import Flask
from flask import render_template, request
from datetime import datetime
from hashlib import md5
from bson.dbref import DBRef

app = Flask(__name__)
morph = pymorphy2.MorphAnalyzer()
monetka = morph.parse('монетка')[0]


class MongoDatabase:
    def __init__(self, host, port, database):
        self.connection = eval('pymongo.MongoClient(host, port).' + database)

    def find_string(self, s):
        return bool(self.connection.coins.find({"string": s}).count())

    def insert_one_coin(self, s, uid):
        self.connection.coins.insert_one(
            {
                "string": s,
                "time": datetime.utcnow(),
                "user": uid,
            }
        )

    def insert_one_transfer(self, _from, to):
        coin = db.connection.coins.find_one({'user': _from})["_id"]
        self.connection.log.insert_one(
            {
                "coin": DBRef('coins', coin),
                "from": _from,
                "to": to,
                "time": datetime.utcnow()
            }
        )

    def get_amount_by_uid(self, uid):
        return self.connection.coins.find({"user": uid}).count()

    def get_top(self):
        sort = {'$sort': {'total': -1}}
        return list(self.connection.coins.aggregate([{'$group': {'_id': '$user', 'total': {'$sum': 1}}}, sort]))[:10]

    def find_user_coins(self, uid):
        return self.connection.coins.find({'user': uid})

    def transfer(self, uid, rid):
        self.connection.coins.replace_one({'user': uid}, {'user': rid})


def get_name_by_uid(uid):
    try:
        session = vk.Session()
        vk_api = vk.API(session, v='5.73')
        res = vk_api.users.get(user_id=uid)
        if 'deactivated' in res[0]:
            raise Exception
        return res[0]['first_name'] + ' ' + res[0]['last_name']
    except:
        return []


db = MongoDatabase('localhost', 27017, 'db')


@app.route('/', methods=['GET', 'POST'])
def index():
    res = []
    if request.method == "POST":
        hashes = request.form["hashes"].strip().split()
        for i, h in enumerate(hashes, 1):
            error = False
            if md5(h.encode('utf8')).hexdigest()[:4] == '0000':  # нашли хеш (здесь проверка для 4-х нулей)
                uid, rest = h.split('-', maxsplit=1)
                if not uid.isdigit():
                    error = True
            else:
                error = True
            res.append((i, h, error))
            if not error and not db.find_string(h):
                db.insert_one_coin(h, uid)
    return render_template('index.html', res=res)


@app.route('/wallet', methods=['GET', 'POST'])
def wallet():
    res = []
    if request.method == "POST":
        wallet_id = request.form["wallet-id"].strip()
        amount = db.get_amount_by_uid(wallet_id)
        if not wallet_id.isdigit():
            res = 'Некорректный формат ID. Попробуйте еще раз.'
        else:
            res = 'У пользователя {} на счету {} {}.'.format(wallet_id, amount,
                                                             monetka.make_agree_with_number(amount).word)
    return render_template('wallet.html', res=res)


@app.route('/send')
def send():
    user_id = False
    if 'code' in request.args:
        code = request.args['code']
        user_id = requests.post('https://oauth.vk.com/access_token', params={
            'client_id': 6241408, 'code': code,
            'client_secret': 'QDu1LBmKCyfP5eNFKguW',
            'redirect_uri': 'http://localhost:8080/send'
        }).json()['user_id']
    return render_template('send.html', user_id=user_id)


@app.route('/send', methods=['POST'])
def send_money():
    uid = False
    receiver = False
    amount = False
    bad = False
    fields = request.form
    if len(fields) == 0:
        return render_template('send.html', msg='Для перевода монеток - авторизируйтесь.')

    elif len(fields) == 3:
        uid = fields['uid']
        receiver = fields['receiver_input']
        amount = fields['amount_input']
        try:
            n_coins = int(amount)
            r = int(receiver)
            user_coins = db.find_user_coins(uid)

            if user_coins.count() < n_coins:
                return render_template('send.html', msg='На вашем счету недостаточно средств.')

            if db.get_amount_by_uid(receiver) == 0:
                return render_template('send.html',
                                       msg='Пользователь не найден. '
                                           'Перевести монетки можно только пользователям сервиса.')

            for i in range(n_coins):
                db.insert_one_transfer(uid, receiver)
                db.transfer(uid, receiver)

            return render_template('send.html', uid=uid, receiver=receiver, amount=amount,
                                   msg='Вы успешно перевели {} мон. на счет пользователя {}.'.format(amount, receiver))
        except ValueError:
            return render_template('send.html', msg='Неправильный формат введенных данных')
    else:
        return render_template('send.html', msg='Пожалуйста, заполните все поля.')


@app.route('/top', methods=['GET', 'POST'])
def top():
    res = []
    for i, elem in enumerate(db.get_top(), 1):
        uid, amount = elem.values()
        name = get_name_by_uid(uid)
        if name:
            res.append((i, name, amount))

    return render_template('top.html', res=res)


if __name__ == '__main__':
    app.run(port=8080, host='localhost')
