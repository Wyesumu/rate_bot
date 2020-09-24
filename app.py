import telebot
import config
from vedis import Vedis
import flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime as dt
import xlsxwriter
from os import mkdir

stages = Vedis('stages.vdb')
temp = Vedis('temp.vdb')
clicks = Vedis('clicks.vdb')

bot = telebot.TeleBot(config.token)


app = flask.Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.db'
db = SQLAlchemy(app)

class User(db.Model):
	id = db.Column(db.Integer, primary_key=True, autoincrement=True)
	user_id = db.Column(db.Integer)
	channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'))

class Channel(db.Model):

	id = db.Column(db.Integer, primary_key=True, autoincrement=True)
	chat_id = db.Column(db.Integer)
	name = db.Column(db.String())
	user_id = db.Column(db.Integer)
	posts = db.relationship('Post', backref='channel', lazy=True)
	users = db.relationship('User', backref='channel', lazy=True)

	def __repr__(self):
		return self.name

class Post(db.Model):
	id = db.Column(db.Integer, primary_key=True, autoincrement=True)
	message_id = db.Column(db.Integer)
	user_id = db.Column(db.Integer)
	channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'))
	data = db.Column(db.String)
	data_type = db.Column(db.String)
	buttons = db.relationship('Button', backref='post', lazy=True)
	time = db.Column(db.DateTime)
	url = db.Column(db.String)

class Button(db.Model):
	id = db.Column(db.Integer, primary_key=True, autoincrement=True)
	data = db.Column(db.String)
	post_id = db.Column(db.Integer, db.ForeignKey('post.id'))
	clicks = db.relationship('Click', backref='button', lazy=True)

class Click(db.Model):
	id = db.Column(db.Integer, primary_key=True, autoincrement=True)
	user_id = db.Column(db.Integer)
	username = db.Column(db.String())
	button_id = db.Column(db.Integer, db.ForeignKey('button.id'))

db.create_all()

def channel_exists(name):
	try:
		bot.get_chat(name)
		return True
	except Exception as e:
		print(e)
		return False

@bot.message_handler(commands=['start'])
def start(message):
	with stages.transaction():
		stages[str(message.chat.id)] = 'start'
	bot.send_message(message.chat.id, 'Отправьте нам ссылку на ваш телеграм канал')

@bot.message_handler(commands=['post'])
def make_post(message):
	with stages.transaction():
		stages[str(message.chat.id)] = 'post_1'
	bot.send_message(message.chat.id, 'Отправьте боту то, что хотите опубликовать. Это может быть всё, что угодно – текст, фото, видео')

@bot.message_handler(commands=['get_users'])
def get_users(message):
	workbook = xlsxwriter.Workbook('users.xlsx', {'in_memory': True})
	worksheet = workbook.add_worksheet()
	worksheet.write(0, 0, 'Ник в Телеграмм')
	worksheet.write(0, 1, 'Куда нажал')
	worksheet.write(0, 2, 'Id поста в канале')
	worksheet.write(0, 3, 'Канал')

	for count, click in enumerate(Click.query.all()):
		worksheet.write(count+1, 0, click.username)
		worksheet.write(count+1, 1, click.button.data)
		worksheet.write(count+1, 2, click.button.post.message_id)
		worksheet.write(count+1, 3, click.button.post.channel.name)

	workbook.close()

	doc = open('users.xlsx', 'rb')
	bot.send_document(message.chat.id, doc)

@bot.message_handler(commands=['change'])
def change_likes(message):
	parted_mes = message.text.split()
	try:
		mes_id = parted_mes[1]
		count_1 = parted_mes[2]
		count_2 = parted_mes[3]
	except IndexError:
		bot.send_message(message.chat.id, 'Ошибка извлечения параметров. Необходимо отправить команду в формате: /change [message_id] [likes first] [likes second]')
		return

	channel = Channel.query.get(User.query.filter_by(user_id=message.chat.id).first().channel_id)
	post = Post.query.filter_by(channel_id=channel.id, message_id=mes_id).first()

	with clicks.transaction():
		clicks['click_first_'+str(post.id)] = count_1
		clicks['click_second_'+str(post.id)] = count_2

	bot.send_message(message.chat.id, "Данные успешно изменены. Количество кликов обновится при следующем уникальном клике")

@bot.message_handler(content_types=["video"])
def video_handler(message):
	if stages[str(message.chat.id)].decode() == 'post_1':
		file_info = bot.get_file(message.video.file_id)
		downloaded_file = bot.download_file(file_info.file_path)
		src = 'img/videos/' + message.video.file_id[20:-20:2] + '.mp4'
		try:
			with open(src, 'wb') as new_file:
				new_file.write(downloaded_file)
		except FileNotFoundError:
			mkdir('img/videos/')
			with open(src, 'wb') as new_file:
				new_file.write(downloaded_file)
		with temp.transaction():
			temp[str(message.chat.id)+'_text'] = src
		with stages.transaction():
			stages[str(message.chat.id)] = 'post_2'
		with temp.transaction():
			temp[str(message.chat.id)+'_post_type'] = 'video'

		markup = telebot.types.InlineKeyboardMarkup()
		kb1 = telebot.types.InlineKeyboardButton(text="Добавить URL-кнопку", callback_data="add_url")
		kb2 = telebot.types.InlineKeyboardButton(text="Добавить реакции", callback_data="add_react")
		markup.add(kb1, kb2)
		bot.send_message(message.chat.id, 'Что хотите добавить?', reply_markup=markup)

@bot.message_handler(content_types=["photo"])
def photo_handler(message):
	if stages[str(message.chat.id)].decode() == 'post_1':
		file_info = bot.get_file(message.photo[-1].file_id)
		downloaded_file = bot.download_file(file_info.file_path)
		src = 'img/' + message.photo[-1].file_id[20:-20:2] + '.jpg'
		try:
			with open(src, 'wb') as new_file:
				new_file.write(downloaded_file)
		except FileNotFoundError:
			mkdir('img/')
			with open(src, 'wb') as new_file:
				new_file.write(downloaded_file)

		with temp.transaction():
			temp[str(message.chat.id)+'_text'] = src
		with stages.transaction():
			stages[str(message.chat.id)] = 'post_2'
		with temp.transaction():
			temp[str(message.chat.id)+'_post_type'] = 'photo'

		markup = telebot.types.InlineKeyboardMarkup()
		kb1 = telebot.types.InlineKeyboardButton(text="Добавить URL-кнопку", callback_data="add_url")
		kb2 = telebot.types.InlineKeyboardButton(text="Добавить реакции", callback_data="add_react")
		markup.add(kb1, kb2)
		bot.send_message(message.chat.id, 'Что хотите добавить?', reply_markup=markup)

def ask_send_post(message):
	markup = telebot.types.InlineKeyboardMarkup()
	kb1 = telebot.types.InlineKeyboardButton(text="Да", callback_data="send_post")
	kb2 = telebot.types.InlineKeyboardButton(text="Отмена", callback_data="cancel_post")
	kb3 = telebot.types.InlineKeyboardButton(text="Сделать отложенный", callback_data="post_later")
	markup.add(kb1, kb2)
	markup.add(kb3)
	bot.send_message(message.chat.id, 'Отравить сейчас?', reply_markup=markup)

@bot.message_handler(content_types=["text"])
def text_handler(message):
	if stages[str(message.chat.id)].decode() == 'post_later':
		try:
			dt.strptime(message.text, '%d/%m/%Y')
			with temp.transaction():
				temp[str(message.chat.id)+'_date'] = message.text

			markup = telebot.types.InlineKeyboardMarkup()
			kb1 = telebot.types.InlineKeyboardButton(text="Да", callback_data="post_later_confirmed")
			kb2 = telebot.types.InlineKeyboardButton(text="Нет", callback_data="cancel_post")
			markup.add(kb1, kb2)
			bot.send_message(message.chat.id, 'Добавить?', reply_markup=markup)
		except:
			bot.send_message(message.chat.id, 'Ошибка формата даты')

	if stages[str(message.chat.id)].decode() == 'post_url':
		if message.text.startswith('http'):
			with temp.transaction():
				temp[str(message.chat.id)+'_button_type'] = 'url'

			with temp.transaction():
				temp[str(message.chat.id)+'_button'] = message.text
			ask_send_post(message)
		else:
			bot.send_message(message.chat.id, 'Недействительная ссылка')

	if stages[str(message.chat.id)].decode() == 'post_react':
		with temp.transaction():
			temp[str(message.chat.id)+'_button_type'] = 'react'

		with temp.transaction():
			temp[str(message.chat.id)+'_button'] = message.text
		ask_send_post(message)

	if stages[str(message.chat.id)].decode() == 'post_1':
		with temp.transaction():
			temp[str(message.chat.id)+'_text'] = message.text
		with stages.transaction():
			stages[str(message.chat.id)] = 'post_2'
		with temp.transaction():
			temp[str(message.chat.id)+'_post_type'] = 'text'

		markup = telebot.types.InlineKeyboardMarkup()
		kb1 = telebot.types.InlineKeyboardButton(text="Добавить URL-кнопку", callback_data="add_url")
		kb2 = telebot.types.InlineKeyboardButton(text="Добавить реакции", callback_data="add_react")
		markup.add(kb1, kb2)
		bot.send_message(message.chat.id, 'Что хотите добавить?', reply_markup=markup)


	if stages[str(message.chat.id)].decode() == 'start':
		if message.text[0] == '@':
			if channel_exists(message.text):
				channel_id = bot.get_chat(message.text).id

				if not User.query.filter_by(user_id=message.chat.id).first():
					new_user = User(user_id=message.chat.id)
					db.session.add(new_user)
					db.session.commit()

				if not Channel.query.filter_by(chat_id = channel_id).first():
					new_channel = Channel(chat_id = channel_id, name = message.text, user_id = message.chat.id)
					db.session.add(new_channel)
					db.session.flush()
					User.query.filter_by(user_id=message.chat.id).first().channel_id = new_channel.id
				else:
					User.query.filter_by(user_id=message.chat.id).first().channel_id = Channel.query.filter_by(chat_id = channel_id).first().id

				db.session.commit()

				markup = telebot.types.InlineKeyboardMarkup()
				kb1 = telebot.types.InlineKeyboardButton(text="В администраторах", callback_data="added_admin")
				markup.add(kb1)
				bot.send_message(message.chat.id, 'Добавьте '+bot.get_me().username+' в администраторы канала и нажмите на кнопку ниже', reply_markup=markup)
			else:
				bot.send_message(message.chat.id, 'Канал не найден')
		else:
			bot.send_message(message.chat.id, 'Адрес канала должен начинаться с @')

@bot.callback_query_handler(func=lambda call:True)
def call_handler(call):

	if call.data == 'post_later':
		with stages.transaction():
			stages[str(call.message.chat.id)] = 'post_later'
		bot.send_message(call.message.chat.id, 'Отправьте дату в формате dd/mm/yyyy')

	if call.data == 'post_later_confirmed':
		buttons = temp[str(call.message.chat.id)+'_button'].decode()
		text = temp[str(call.message.chat.id)+'_text'].decode()
	
		try:
			new_post = Post(user_id=call.message.chat.id,
					channel_id=Channel.query.filter_by(user_id=call.message.chat.id).first().id,
					data = text,
					data_type=temp[str(call.message.chat.id)+'_post_type'].decode(),
					time=dt.strptime(temp[str(call.message.chat.id)+'_date'].decode(), '%d/%m/%Y'))
		except AttributeError:
			bot.send_message(call.message.chat.id, 'Отсутсвует канал в базе, добавьте новый командой /start')
			return
		db.session.add(new_post)
		db.session.flush()

		if temp[str(call.message.chat.id)+'_button_type'].decode() == 'url':
			new_post.url = temp[str(call.message.chat.id)+'_button'].decode()
			

		if temp[str(call.message.chat.id)+'_button_type'].decode() == 'react':
			buttons = buttons.split()

			for button in buttons:
				new_button = Button(data = button, post_id = new_post.id)
				db.session.add(new_button)

			#new_post.message_id = sent_mes.message_id

		db.session.commit()

	if call.data == 'cancel_post':
		with stages.transaction():
			stages[str(message.chat.id)] = 'none'
		bot.send_message(call.message.chat.id, "Отменено")

	if call.data == 'send_post':
		buttons = temp[str(call.message.chat.id)+'_button'].decode()
		text = temp[str(call.message.chat.id)+'_text'].decode()
		
		
		try:
			new_post = Post(user_id=call.message.chat.id,
					channel_id=Channel.query.filter_by(user_id=call.message.chat.id).first().id,
					data = text,
					data_type=temp[str(call.message.chat.id)+'_post_type'].decode(),
					time=None)
		except AttributeError:
			bot.send_message(call.message.chat.id, 'Отсутсвует канал в базе, добавьте новый командой /start')
			return
		db.session.add(new_post)
		db.session.flush()

		if temp[str(call.message.chat.id)+'_button_type'].decode() == 'url':
			new_post.url = temp[str(call.message.chat.id)+'_button'].decode()
			markup = telebot.types.InlineKeyboardMarkup()
			kb1 = telebot.types.InlineKeyboardButton(text="Перейти на сайт", url=temp[str(call.message.chat.id)+'_button'].decode())
			markup.add(kb1)
			if temp[str(call.message.chat.id)+'_post_type'].decode() == 'text':
				sent_mes = bot.send_message(Channel.query.filter_by(user_id=call.message.chat.id).first().name,
					text,
					reply_markup=markup)
			elif temp[str(call.message.chat.id)+'_post_type'].decode() == 'photo':
				with open(text, 'rb') as photo:
					sent_mes = bot.send_photo(Channel.query.filter_by(user_id=call.message.chat.id).first().name, 
						photo = photo,
						reply_markup=markup)
			elif temp[str(call.message.chat.id)+'_post_type'].decode() == 'video':
				with open(text, 'rb') as video:
					sent_mes = bot.send_video(Channel.query.filter_by(user_id=call.message.chat.id).first().name, 
						video,
						reply_markup=markup)
			

		if temp[str(call.message.chat.id)+'_button_type'].decode() == 'react':
			buttons = buttons.split()
						
			markup = telebot.types.InlineKeyboardMarkup()
			try:
				kb1 = telebot.types.InlineKeyboardButton(text=buttons[0], callback_data="click_first_"+str(new_post.id))
				kb2 = telebot.types.InlineKeyboardButton(text=buttons[1], callback_data="click_second_"+str(new_post.id))
			except IndexError:
				with stages.transaction():
					stages[str(call.message.chat.id)] = 'post_react'
				bot.send_message(call.message.chat.id, "Ошибка, отправьте две Emoji через пробел")
				return
			markup.add(kb1, kb2)
			if temp[str(call.message.chat.id)+'_post_type'].decode() == 'text':
				sent_mes = bot.send_message(Channel.query.filter_by(user_id=call.message.chat.id).first().name,
					text,
					reply_markup=markup)
			elif temp[str(call.message.chat.id)+'_post_type'].decode() == 'photo':
				with open(text, 'rb') as photo:
					sent_mes = bot.send_photo(Channel.query.filter_by(user_id=call.message.chat.id).first().name, 
						photo = photo,
						reply_markup=markup)
			elif temp[str(call.message.chat.id)+'_post_type'].decode() == 'video':
				with open(text, 'rb') as video:
					sent_mes = bot.send_video(Channel.query.filter_by(user_id=call.message.chat.id).first().name, 
						video,
						reply_markup=markup)

			for button in buttons:
				new_button = Button(data = button, post_id = new_post.id)
				db.session.add(new_button)

			new_post.message_id = sent_mes.message_id

		db.session.commit()

	if call.data == 'add_url':
		with stages.transaction():
			stages[str(call.message.chat.id)] = 'post_url'
		bot.send_message(call.message.chat.id, 'Отправьте ссылку')

	if call.data == 'add_react':
		with stages.transaction():
			stages[str(call.message.chat.id)] = 'post_react'
		bot.send_message(call.message.chat.id, 'Отправьте две реакции через пробел')

	if call.data == 'added_admin':
		try:
			if bot.get_chat_member(Channel.query.filter_by(user_id=call.message.chat.id).first().chat_id, bot.get_me().id).can_post_messages:
				bot.send_message(call.message.chat.id, 'Успешно')
			else:
				bot.send_message(call.message.chat.id, 'Ошибка: бот не администратор, попробуйте снова')
				markup = telebot.types.InlineKeyboardMarkup()
				kb1 = telebot.types.InlineKeyboardButton(text="В администраторах", callback_data="added_admin")
				markup.add(kb1)
				bot.send_message(call.message.chat.id, 'Добавьте '+bot.get_me().username+' в администраторы канала и нажмите на кнопку ниже', reply_markup=markup)
		except Exception as e:
			print(e)
			bot.send_message(call.message.chat.id, 'Ошибка: '+str(e)+', попробуйте снова')
			markup = telebot.types.InlineKeyboardMarkup()
			kb1 = telebot.types.InlineKeyboardButton(text="В администраторах", callback_data="added_admin")
			markup.add(kb1)
			bot.send_message(call.message.chat.id, 'Добавьте '+bot.get_me().username+' в администраторы канала и нажмите на кнопку ниже', reply_markup=markup)


	if call.data.startswith('click_first_'):
		
		p_id = int(call.data[12:])
		post = Post.query.get(p_id)
		if not post:
			return
		if not Click.query.filter_by(user_id=call.from_user.id, button_id=post.buttons[1].id).first() and not Click.query.filter_by(user_id=call.from_user.id, button_id=post.buttons[0].id).first():
			bot.answer_callback_query(call.id, text="Ответ принят")
			with clicks.transaction():
				clicks.incr(call.data)

			try:
				clicks['click_second_'+str(post.id)].decode()
			except:
				with clicks.transaction():
					clicks['click_second_'+str(post.id)] = 0

			new_click = Click(user_id=call.from_user.id, username=call.from_user.username, button_id=post.buttons[0].id)
			db.session.add(new_click)
			db.session.commit()
		else:
			bot.answer_callback_query(call.id, text="Вы уже ответили")

		markup = telebot.types.InlineKeyboardMarkup()
		kb1 = telebot.types.InlineKeyboardButton(text=post.buttons[0].data + clicks[call.data].decode(), callback_data=call.data)
		kb2 = telebot.types.InlineKeyboardButton(text=post.buttons[1].data + clicks['click_second_'+str(post.id)].decode(), callback_data='click_second_'+str(post.id))
		markup.add(kb1, kb2)
		try:
			bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup = markup)
		except:
			pass

	if call.data.startswith('click_second_'):
		
		p_id = int(call.data[13:])
		post = Post.query.get(p_id)
		if not post:
			return
		if not Click.query.filter_by(user_id=call.from_user.id, button_id=post.buttons[1].id).first() and not Click.query.filter_by(user_id=call.from_user.id, button_id=post.buttons[0].id).first():
			bot.answer_callback_query(call.id, text="Ответ принят")
			with clicks.transaction():
				clicks.incr(call.data)

			try:
				clicks['click_first_'+str(post.id)].decode()
			except:
				with clicks.transaction():
					clicks['click_first_'+str(post.id)] = 0

			new_click = Click(user_id=call.from_user.id, username=call.from_user.username, button_id=post.buttons[1].id)
			db.session.add(new_click)
			db.session.commit()
		else:
			bot.answer_callback_query(call.id, text="Вы уже ответили")

		markup = telebot.types.InlineKeyboardMarkup()
		kb1 = telebot.types.InlineKeyboardButton(text=post.buttons[0].data + clicks['click_first_'+str(post.id)].decode(), callback_data='click_first_'+str(post.id))
		kb2 = telebot.types.InlineKeyboardButton(text=post.buttons[1].data + clicks[call.data].decode(), callback_data=call.data)
		
		markup.add(kb1, kb2)
		try:
			bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup = markup)
		except:
			pass

if __name__ == '__main__':
	bot.polling(none_stop=True)