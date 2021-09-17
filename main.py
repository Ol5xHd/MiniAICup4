import json
import random
import queue
import time


# класс глобальных параметров, содержит настройки игры
class GlobalParams:
	xCellsCount = None # ширина поля
	yCellsCount = None # высота поля
	width = None # ширина одной большой ячейки в элементарных ячейках
	bonuses = [] # массив бонусов, без изменений берётся из ввода
	tickNum  = None # глобальный номер текущего тика
	speed = None # глобальная скорость игроков по умолчанию
	maxTickCount = None # максимальное количество тиков в игре
	
	def __str__(self):
		result = (
			'xCellsCount = {0}'
			', yCellsCount = {1}'
			', width = {2}'
			', tickNum = {3}'
			', speed = {4}'.format(
				self.xCellsCount, self.yCellsCount, self.width, self.tickNum, self.speed
			)
		)
		return result

# класс игрока; содержит всю информацию о состоянии игрока
class Player:
	score = None # счёт игрока
	direction = None # направленеи игрока
	sign = None # индивидуальный знак игрока
	territory = [] # территория
	position = [] # текущая позиция в элементарных ячейках
	trace = [] # след
	bonuses = [] # бонусы
	traceStart = [] # точка, в которой начался путь игрока; нужно только для меня при рассчёте замкнутого пути домой

	def __init__(self, sign):
		self.sign = sign

	def __str__(self):
		result = (
			'score = {0}'
			', direction = {1}'
			', sign = {2}'
			', territory = {3}'
			', position = {4}'
			', trace = {5}'
			', bonuses = {6}'.format(
				self.score, self.direction, self.sign, self.territory, self.position, self.trace, self.bonuses
			)
		)
		return result


	# вычислить будущую скорость игрока после нескольких пройденных клеток на основе глобальной скорости и бонусов игрока
	# moves_made - количество сделанных ходов (пройденных центров клеток)
	def FutureSpeed(self, moves_made):
		future_speed = GLOBAL_PARAMS.speed
		nitro_cells = 0
		slow_cells = 0

		# считываем, сколько времени бонусы будут активны
		for bonus in self.bonuses:
			if bonus['type'] == 'n':
				nitro_cells = bonus['ticks']
			if bonus['type'] == 's':
				slow_cells = bonus['ticks']

		# уменьшаем время активности бонусов на количество сделанных ходов
		nitro_cells -= moves_made
		slow_cells -= moves_made

		if (
			nitro_cells > 0 and slow_cells > 0 # оба бонуса ещё активны, на скорости не отразится
			or
			nitro_cells <= 0 and slow_cells <= 0 # оба бонуса уже не активны, на скорости не отразится
		):
			pass
		elif nitro_cells > 0 and slow_cells <= 0: # активно только ускорение, увеличим скорость
			while future_speed < GLOBAL_PARAMS.width:  # увеличиваем скорость, пока она не будет нацело делить ширину клетки
				future_speed += 1
				if GLOBAL_PARAMS.width % future_speed == 0:
					break
		elif nitro_cells <= 0 and slow_cells > 0: # активно только замедление, уменьшим скорость
			while future_speed > 1:  # уменьшаем скорость, пока она не будет нацело делить ширину клетки
				future_speed -= 1
				if GLOBAL_PARAMS.width % future_speed == 0:
					break

		# где-то на поле есть нитро
		# потенциально противник может его взять и все расчёты пойдут прахом, поэтому берём оценку сверху
		# неэкономично, зато безопасно
		if self.sign != 'i': # разумеется, такой хак нужен только для противников
			if future_speed == GLOBAL_PARAMS.speed and GAME_FIELD.ExistsNitroOnField():
				while future_speed < GLOBAL_PARAMS.width:  # увеличиваем скорость, пока она не будет нацело делить ширину клетки
					future_speed += 1
					if GLOBAL_PARAMS.width % future_speed == 0:
						break

		return future_speed


	# рассчитать текущую скорость игрока
	def CurrentSpeed(self):
		return self.FutureSpeed(0)


# класс клетки; содержит информацию о том, что на этой клетке происходит
class Cell:
	position = [] # позциция клетки
	signs = {} # различные статусы клетки: 'territory', 'trace', 'bonus': 'n' - Ускорение, 's' - Замедление, 'saw' - пила
	
	def __init__(self, x, y):
		self.position = [x, y]
		self.signs = {'territory': None, 'trace': None, 'bonus': None}

	def __init__(self, position):
		self.position = position.copy()
		self.signs = {'territory': None, 'trace': None, 'bonus': None}

	def Clear(self):
		self.signs['territory'] = None
		self.signs['trace'] = None
		self.signs['bonus'] = None

	def __str__(self):
		result = (
			'position = {0}'
			', territory = {1}'
			', trace = {2}'
			', player = {3}'
			', bonus = {4}'.format(
				self.position, self.signs['territory'], self.signs['trace'], self.signs['player'], self.signs['bonus']
			)
		)
		return result


# класс игрового поля
# представляет собой словарь, где ключ - строковое представление координат ячейки, а значение - сама ячейка
class GameField:
	field = {} # словарь игровых клеток, ключ каждой клетки - это её середина, ключи - стрингованные листы
	bonuses = None

	def __init__(self):
		self.field = {}
	
	# не совсем безопасное взятие клетки по координатам
	# границы поля учитываются, а вот "точность координат" - нет
	# если, например, игрок находится не в центре клетки, то здесь "сядем в лужу"
	# отдаём этот момент на откуп коду снаружи; запросил чушь - сам дурак
	def __getitem__(self, position):
		if position[0] < 0 or position[0] >= GLOBAL_PARAMS.xCellsCount * GLOBAL_PARAMS.width:
			return None
		if position[1] < 0 or position[1] >= GLOBAL_PARAMS.yCellsCount * GLOBAL_PARAMS.width:
			return None
		
		return self.field[str(position)]
	
	def __setitem__(self, position, cell):
		self.field[str(position)] = cell

	# очистить поле - стереть все метки с клеток
	def ClearField(self):
		self.bonuses = None
		for key in self.field:
			self.field[key].Clear()

	def ExistsNitroOnField(self):
		exists = False
		if self.bonuses is not None:
			for elem in self.bonuses:
				if elem['type'] == 'n':
					exists = True
					break
		return exists

	def __str__(self):
		result = ''
		for key in self.field:
			result += key
			result += ' = '
			result += str(self.field[key])
			result += ', '
		result = result[:-2]
		return result


# нормализация координат - смещение в середину клетки
# нет проверки корректности координат
def NormalizePosition(position):
	x = position[0]
	quotient = x // GLOBAL_PARAMS.width
	norm_x = quotient * GLOBAL_PARAMS.width + GLOBAL_PARAMS.width // 2

	y = position[1]
	quotient = y // GLOBAL_PARAMS.width
	norm_y = quotient * GLOBAL_PARAMS.width + GLOBAL_PARAMS.width // 2

	return [norm_x, norm_y]


# прочитать информацию об игроке
def ReadPlayer(player, json_player_state):
	player.score = json_player_state['score']
	player.direction = json_player_state['direction']

	player.territory = json_player_state['territory']
	for position in player.territory:
		curr_cell = GAME_FIELD[position]
		if curr_cell is not None:
			curr_cell.signs['territory'] = player.sign

	player.position = json_player_state['position']
	
	player.trace = json_player_state['lines']

	if len(player.trace) == 1: # запоминаем, с какой клетки начался маршрут игрока
		player.traceStart = player.trace[0].copy()
	elif len(player.trace) == 0: # обнуляем точку начала маршрута, если маршрута больше нет
		player.traceStart = None

	for position in player.trace:
		curr_cell = GAME_FIELD[position]
		if curr_cell is not None:
			curr_cell.signs['trace'] = player.sign

	player.bonuses = json_player_state['bonuses']


# прочитать информацию о бонусах на поле
def ReadBonuses(bonuses_json):
	GAME_FIELD.bonuses = bonuses_json
	for elem in bonuses_json:
		bonus_cell = GAME_FIELD[elem['position']]
		if bonus_cell is not None:
			bonus_cell.signs['bonus'] = elem['type']


# обработать ввод
def ParseInput(input_str):
	input_json = json.loads(input_str)
	input_type = input_json['type']
	json_params = input_json['params']
	
	if input_type == 'start_game':
		GLOBAL_PARAMS.xCellsCount = json_params['x_cells_count']
		GLOBAL_PARAMS.yCellsCount = json_params['y_cells_count']
		GLOBAL_PARAMS.width = json_params['width']
		GLOBAL_PARAMS.speed = json_params['speed']
		if 'max_tick_count' in json_params:
			GLOBAL_PARAMS.maxTickCount = json_params['max_tick_count']
		else: # заглушка для ЛРа - он не отдаёт max_tick_count в начале игры
			GLOBAL_PARAMS.maxTickCount = 1500

		# создание игрового поля
		for x_cell in range(0, GLOBAL_PARAMS.xCellsCount):
			for y_cell in range(0, GLOBAL_PARAMS.yCellsCount):
				x_pos = int(x_cell * GLOBAL_PARAMS.width + GLOBAL_PARAMS.width // 2)
				y_pos = int(y_cell * GLOBAL_PARAMS.width + GLOBAL_PARAMS.width // 2)
				key = [x_pos, y_pos]
				GAME_FIELD[key] = Cell(key)
	
	elif input_type == 'tick':
		ANOTHER_PLAYERS.clear()
		json_players = json_params['players']

		for player_sign in json_players:
			json_player_state = json_players[player_sign]
			if player_sign == 'i': # обработка игрока-меня
				ReadPlayer(PLAYER_ME, json_player_state)
			else: # обработка другого игрока
				ANOTHER_PLAYERS[player_sign] = Player(player_sign)
				ReadPlayer(ANOTHER_PLAYERS[player_sign], json_player_state)

		ReadBonuses(json_params['bonuses'])
		GLOBAL_PARAMS.tickNum = json_params['tick_num']
	
	return input_type


# получить противоположную команду
def GetOppositeCommand(command):
	if command == 'left':
		return 'right'
	elif command == 'right':
		return 'left'
	elif command == 'up':
		return 'down'
	elif command == 'down':
		return 'up'
	else:
		return None


# имея позицию и команду, получить позицию, куда ведёт переданная команда
def GetPositionByCommand(position, command):
	new_position = position.copy()
	if command == 'left':
		new_position[0] = position[0] - GLOBAL_PARAMS.width
	elif command == 'right':
		new_position[0] = position[0] + GLOBAL_PARAMS.width
	elif command == 'down':
		new_position[1] = position[1] - GLOBAL_PARAMS.width
	elif command == 'up':
		new_position[1] = position[1] + GLOBAL_PARAMS.width

	return new_position


# получить смежную ячейку относительно pos_list, куда ведёт команда command
# возвращает None, если ячейки не существует
def GetAdjacentCell(pos_list, command):
	new_position = GetPositionByCommand(pos_list, command)
	
	return GAME_FIELD[new_position]


# разрешено ли передвинуться по команде command
# нельзя передвигаться за границы поля и на свой собственный след
# в некоторых случаях разрешаем пересекать свой след - см. параметр can_cross_trace
def IsAbleToMove(position, sign, command, can_cross_trace):
	able_to_move = True
	
	adjacent_cell = GetAdjacentCell(position, command) # попытались получить смежную ячейку
	if adjacent_cell is None: # нет смежной ячейки
		able_to_move = False
	elif ( # смежная ячейка есть
		not can_cross_trace  # пришёл флаг, что нельзя пересекать свой след
		and adjacent_cell.signs['trace'] == sign # смежная ячейка - собственный след игрока
	):
		able_to_move = False
	
	return able_to_move


# получить список доступных для игрока возможных команд; некорректными считаются:
# - команды, противоположные направлению движения
# - команды, которые ведут на ячейки, куда нельзя передвинуться (за границы поля или на свой собственный след)ы
def GetAbleCommands(direction, position, sign, can_cross_trace):
	commands = ['up', 'right', 'down', 'left']

	# удаление противоположной команды, поскольку она игнорируется средой
	if direction is not None:
		commands.remove(GetOppositeCommand(direction))
	
	# удаление команд, которые ведут на ячейки, куда нельзя перейти
	commands_to_delete = []
	for cmd_iter in commands:
		if not IsAbleToMove(position, sign, cmd_iter, can_cross_trace):
			commands_to_delete.append(cmd_iter)
	
	able_commands = [cmd for cmd in commands if cmd not in commands_to_delete]
	
	return able_commands


# получить соседние клетки для алгоритма поиска пути
# ищутся только клетки, на которые можно перейти
def PositionsToMove(direction, position, sign, may_cross_trace):
	neighbors = []

	commands = GetAbleCommands(direction, position, sign, may_cross_trace)
	for cmd in commands:
		new_position = GetPositionByCommand(position, cmd)
		neighbors.append(new_position)

	return neighbors


# получить ближайший для игрока центр клетки с учётом его направления движения
def GetClosestCenter(player):
	closest_center = NormalizePosition(player.position) # нормализовали позицию игрока
	if player.direction == 'up' and closest_center[1] < player.position[1]: # игрок двигается вверх и вышел из ближайшего центра
		closest_center[1] += GLOBAL_PARAMS.width # сдвигаем центр наверх
	elif player.direction == 'right' and closest_center[0] < player.position[0]:
		closest_center[0] += GLOBAL_PARAMS.width
	elif player.direction == 'down' and closest_center[1] > player.position[1]:
		closest_center[1] -= GLOBAL_PARAMS.width
	elif player.direction == 'left' and closest_center[0] > player.position[0]:
		closest_center[0] -= GLOBAL_PARAMS.width

	return closest_center


# просчитать словарь, где ключ - позиция ячейки, а значение - через сколько тиков там окажется любой противник
# если других активных игроков уже нет, вернёт пустой словарь
def CalcEnemyWillComeIn():
	result = {}

	enemies_will_come_in = []
	for sign in ANOTHER_PLAYERS: # для каждого игрока построим отдельный словарь
		player = ANOTHER_PLAYERS[sign]

		closest_center = GetClosestCenter(player) # ближайший к игроку центр (с учётом его направления и позиции), он же - начало расчёта
		# время до прибытия игрока на ближайшую ячейку
		# до ближайшего центра игрок будет идти с текущей скоростью
		ticks_to_come = max(
			abs(closest_center[0] - player.position[0]),
			abs(closest_center[1] - player.position[1])
		) // player.CurrentSpeed()

		curr_enemy_will_come_in = {} # cсловарь текущего игрока
		direction = {} # словарь, где ключ - позиция ячейки, а значение - направление игрока на этой ячейке
		moves_made = {} # словарь, где ключ - позиция ячейки, а значение - количество сделанных к этой ячейке ходов - нужно для расчёта скорости на этой ячейке

		frontier = queue.Queue() # расширяющаяся граница поиска
		frontier.put(closest_center) # кладём в границу начало поиска
		curr_enemy_will_come_in[str(closest_center)] = ticks_to_come # запоминаем, сколько времени идти до этой клетки
		direction[str(closest_center)] = player.direction # запоминаем направление игрока на этой ячейке

		# запомним, сколько ходов было сделано до стартовой расчётной ячейки
		if ticks_to_come == 0: # начали расчёт уже с центра ячейки
			moves_made[str(closest_center)] = 0
		if ticks_to_come != 0: # в первый (ближайший) центр пришлось идти, поэтому там бонусы игрока потеряют одно значение
			moves_made[str(closest_center)] = 1

		while not frontier.empty(): # пока не все клетки просчитаны
			curr_pos = frontier.get()

			# получаем доступные для перехода соседние клетки;
			# считаем, что противники могут пересекать свой след -
			# это сделано, чтобы учесть ситуацию, когда противник завершает захват территории,
			# 	его след исчезает, и резко меняется география доступных ему ходов
			positions_to_move = PositionsToMove(direction[str(curr_pos)], curr_pos, player.sign, CAN_CROSS_TRACE)
			for next_pos in positions_to_move:
				if str(next_pos) not in curr_enemy_will_come_in: # если текущая клетка ещё не "засветилась" в расчёте
					# противник придёт на следующую ячейку за время, за которое он пришёл на предыдущую ячейку, плюс
					# 	время, которое ему понадобится, чтобы пройти одну клетку с той скоростью, которая у него будет на исходной ячейке
					frontier.put(next_pos)
					curr_enemy_will_come_in[str(next_pos)] =\
						curr_enemy_will_come_in[str(curr_pos)] + GLOBAL_PARAMS.width // player.FutureSpeed(moves_made[str(curr_pos)])
					direction[str(next_pos)] = GetCommandFromTo(curr_pos, next_pos)
					moves_made[str(next_pos)] = moves_made[str(curr_pos)] + 1

		# когда завершён рассчёт для текущего игрока, словарь можно добавить в общий список
		enemies_will_come_in.append(curr_enemy_will_come_in)
	# for sign in ANOTHER_PLAYERS:

	# в этой точке имеем список словарей enemies_will_come_in

	if enemies_will_come_in != []: # если других активных игроков нет, результат формировать не из чего
		# если игроки есть, то сформируем один общий словарь
		# возьмём для каждой клетки минимальное значение среди всех словарей
		for x_cell in range(0, GLOBAL_PARAMS.xCellsCount):
			x_coor = (x_cell * GLOBAL_PARAMS.width) + (GLOBAL_PARAMS.width // 2)
			for y_cell in range(0, GLOBAL_PARAMS.yCellsCount):
				y_coor = (y_cell * GLOBAL_PARAMS.width) + (GLOBAL_PARAMS.width // 2)
				curr_pos = [x_coor, y_coor] # координаты текущей рассматриваемой клетки

				min_value = None # минимальное значение среди словарей
				for dict in enemies_will_come_in: # для каждого словаря
					dict_value = dict[str(curr_pos)] # смотрим значение на текущей клетке в текущем словаре
					if min_value is None or dict_value < min_value: # если минимальное ещё не найдено или если текущее меньше наименьшего найденного
						min_value = dict_value # то теперь считаем ЕГО наименьшим

				result[str(curr_pos)] = min_value # в результат положили наименьшее значение

	return result


# функция сравнения для сортировки списка по времени прихода противника на клетку
def SortingMeasure(pos):
	return ENEMY_WILL_COME_IN[str(pos)]


# просто получить соседей переданной клетки, НЕ учитывая границы игрового поля
def AdjacentPositionsWithNone(position):
	adjacent_positions = []

	commands = ['up', 'right', 'down', 'left']
	for cmd in commands:
		neighbor = GetPositionByCommand(position, cmd)
		adjacent_positions.append(neighbor)

	return adjacent_positions


# просто получить соседей переданной клетки, учитывая границы игрового поля
def AdjacentPositions(position):
	adjacent_positions = []

	commands = ['up', 'right', 'down', 'left']
	for cmd in commands:
		adjacent_cell = GetAdjacentCell(position, cmd)
		if adjacent_cell is not None:
			adjacent_positions.append(adjacent_cell.position.copy())

	return adjacent_positions


# попытаться по своей территории добраться от конечной ячейки маршрута до стартовой (или наоборот - не важно)
# т.е. верно ли, что маршрут выходит и возвращается в одну и ту же компоненту связности
# метод используется только для игрока-меня
def IsExistsPathThroughMyTerritory(start_pos, end_pos):
	successful_search = False  # был ли поиск успешным

	visited = {}  # словарь просмотренных клеток

	# обрабатываем начало поиска - конец маршрута (маршрут заканчивется на моей территории, поэтому можно)
	frontier = queue.Queue()
	frontier.put(end_pos)
	visited[str(end_pos)] = True

	while not frontier.empty():
		current_position = frontier.get()
		if current_position == start_pos:
			successful_search = True
			break

		# пока не нашли, перебираем соседей
		adjacent_positions = AdjacentPositions(current_position)

		# убираем клетки, по котором нельзя прокладывать путь
		bad_positions = []
		for pos in adjacent_positions:
			adjacent_cell = GAME_FIELD[pos]
			if adjacent_cell.signs['territory'] != 'i' and adjacent_cell.position != start_pos: # клетки не моей территории, за исключением начала пути
				bad_positions.append(pos)
			if adjacent_cell.signs['trace'] is not None and adjacent_cell.position != start_pos: # клетки чьего-то следа, за исключением начала пути
				bad_positions.append(pos)

		good_positions = [pos for pos in adjacent_positions if pos not in bad_positions]

		for next_position in good_positions:  # просматриваем соседа
			if str(next_position) not in visited:
				frontier.put(next_position)
				visited[str(next_position)] = True

	return successful_search


# служебный метод, нужен для GetRouteToClosest
# перебирает доступные для перехода клетки и удалет те, на которые нельзя перейти согласно переданным параметрам
def ProcessPositionsToMove(positions_to_move, with_priority, me_to_home):
	if (
		with_priority  # передан флаг приоритезации направлений движения
		and ENEMY_WILL_COME_IN != {} # есть смысл сортировать по приоритетам, т.к. противники ещё есть
	):
		positions_to_move.sort(key=SortingMeasure, reverse = True)  # соседи с наибольшим ENEMY_WILL_COME_IN будут рассмотрены в первую очередь

	# если ищется мой путь домой, нужна особая обработка
	if me_to_home:
		positions_to_del = []
		for next_pos in positions_to_move:
			# если ищем путь домой для себя, то запретим пересекать чужой след ВООБЩЕ
			next_cell = GAME_FIELD[next_pos]
			if next_cell.signs['trace'] is not None:
				positions_to_del.append(next_pos)

			# запретим себе при возвращении домой проходить по клеткам с замедлением
			if next_cell.signs['bonus'] == 's':
				positions_to_del.append(next_pos)

		for pos in positions_to_del:
			if pos in positions_to_move:
				positions_to_move.remove(pos)


# находит путь к ближайщей к игроку клетке определённого типа и счтиает время на этот путь
# результат вовзвращается в качетсве списка
# если клетка искомого типа не была найдена, оба значения вернутся None
# если игрок уже на искомой клетке, вернёт пустой список и 0 тиков
# player - игрок, чей путь считаем
# owners_list - список владельцев, чьи клетки ищем
# search_type - тип поиска: trace, empty, territory, nitro
# moves_made_before - количество ходов, сделанных до запуска поиска пути; нужно для рассчёта скорости
# can_cross_trace - можно ли при расчёте пути пересекать свой собственный след
# актуально только для игрока-меня:
# - with_priority - если True, путь будет проложен по клеткам как можно дальше от противников
def GetRouteToClosest(player, owners_list, search_types, with_priority, moves_made_before, can_cross_trace):
	result = {'path': None, 'ticks': None}

	me_to_home = False # признак того, что ищется путь для меня домой; это особая ситуация с хитрыми обработками, поэтому заводим отдельный флаг
	if player.sign == 'i' and owners_list == ['i'] and search_types == ['territory']:
		me_to_home = True

	closest_center = GetClosestCenter(player) # ближайшая ячейка к игроку с учётом его скорости и направления, это же и начало поиска
	ticks_to_come = max(
		abs(closest_center[0] - player.position[0]),
		abs(closest_center[1] - player.position[1])
	) // player.CurrentSpeed()

	came_from = {} # словарь, где ключ - позиция ячейки, а значение - откуда на неё пришли
	direction = {} # словарь, где ключ - позиция ячейки, а значение - направление игрока на этой ячейке
	come_in = {} # словарь, где ключ - позиция ячейки, а значение - за сколько тиков туда пришли
	moves_made = {}  # словарь, где ключ - позиция ячейки, а значение - количество сделанных к этой ячейке ходов

	# обрабатываем начало поиска
	frontier = queue.Queue()
	frontier.put(closest_center)
	came_from[str(closest_center)] = None
	direction[str(closest_center)] = player.direction
	come_in[str(closest_center)] = ticks_to_come

	# запомним, сколько ходов было сделано до каждой ячейки
	if ticks_to_come == 0:  # начали расчёт уже с центра ячейки
		moves_made[str(closest_center)] = moves_made_before
	if ticks_to_come != 0:  # в первый (ближайший) центр пришлось идти
		moves_made[str(closest_center)] = moves_made_before + 1

	successful_search = False # был ли поиск успешным
	destination = None # точка, которую нашли в результате поиска
	while not frontier.empty():
		current_position = frontier.get()
		curr_cell = GAME_FIELD[current_position]
		if ( # условия прекращения поиска
			'trace' in search_types and curr_cell.signs['trace'] in owners_list
			or 'empty' in search_types and curr_cell.signs['territory'] is None
			or 'territory' in search_types and curr_cell.signs['territory'] in owners_list
			or 'nitro' in search_types and curr_cell.signs['bonus'] == 'n'
			# or что-то ещё
		):
			if me_to_home: # особый случай; надо проверить, что есть путь от начала маршрута до его конца по моей территории
				pos_start = player.traceStart
				if pos_start is None:
					pos_start = PLAYER_ME.position
				if IsExistsPathThroughMyTerritory(pos_start, current_position): # есть путь по моей территории, всё хорошо
					# этот пункт назначения точно хороший
					destination = current_position
					successful_search = True
					break
				else:
					# нет пути по моей территории; результат не подходит нам
					# но запомнить надо
					if destination is None:
						destination = current_position
						successful_search = True
			else: # общий случай, не нужны дополнительные проверки
				# нашли, что хотели, прекращаем поиск
				destination = current_position
				successful_search = True
				break
		
		# пока не нашли, перебираем соседние клетки, на которые можно перейти
		positions_to_move = PositionsToMove(direction[str(current_position)], current_position, player.sign, can_cross_trace)

		# время, за которое придём на соседнюю клетку
		come_in_next_position_time = come_in[str(current_position)] + GLOBAL_PARAMS.width // player.FutureSpeed(moves_made[str(current_position)])

		# исключим недопустимые для перехода клетки согласно переданным параметрам
		ProcessPositionsToMove(positions_to_move, with_priority, me_to_home)
		
		for next_position in positions_to_move: # просматриваем соседей
			if str(next_position) not in came_from:
				frontier.put(next_position)
				came_from[str(next_position)] = current_position
				direction[str(next_position)] = GetCommandFromTo(current_position, next_position)
				come_in[str(next_position)] = come_in_next_position_time
				moves_made[str(next_position)] = moves_made[str(current_position)] + 1

	# конструируем маршрут
	if successful_search:
		result['ticks'] = come_in[str(destination)]
		result['path'] = []
		current_position = destination
		while current_position != closest_center:
			result['path'].append(current_position.copy())
			current_position = came_from[str(current_position)]

		result['path'].reverse()

	return result


# последний довод королей - рандомная команда
def GetRandomCommand(player):
	cmd = None

	able_commands = GetAbleCommands(player.direction, player.position, player.sign, CAN_NOT_CROSS_TRACE)
	if able_commands != []:
		cmd = random.choice(able_commands)
	else:
		cmd = random.choice(['up', 'right', 'down', 'left'])
	
	return cmd


def Debug(msg):
	f = open("out.txt", "a")
	print(msg, file = f)
	f.close()


# получить текстовую команду, ведущую от ячейки pos_from к ячейке pos_to
def GetCommandFromTo(pos_from, pos_to):
	cmd = None
	if pos_to[0] > pos_from[0]:
		cmd = 'right'
	if pos_to[0] < pos_from[0]:
		cmd = 'left'
	if pos_to[1] > pos_from[1]:
		cmd = 'up'
	if pos_to[1] < pos_from[1]:
		cmd = 'down'

	return cmd


# посчитать диагональное расстояние между двумя клетками
def CalcDistance(position_1, position_2):
	return ((position_1[0] - position_2[0])**2 + (position_1[1] - position_2[1])**2)*0.5


# определить, собираюсь ли я двигаться навстречу своему собственному следу
def TowardsMyTrace(current_pos, target_pos):
	towards_my_trace = False
	direction = GetCommandFromTo(current_pos, target_pos)

	adjacent_cell = GetAdjacentCell(current_pos, direction)
	while adjacent_cell is not None and adjacent_cell.signs['territory'] != 'i':
		if adjacent_cell.signs['trace'] == 'i':
			towards_my_trace = True
			break
		adjacent_cell = GetAdjacentCell(adjacent_cell.position, direction)

	return towards_my_trace


# проверяет на безопасность клетку, как часть пути
# клетка считается безопасной, если для перехода на неё или на соседнюю с ней клетку противнику понадобится больше времени,
# 	чем мне для перехода на эту клетку
def IsRouteStepSafe(position, time_limit):
	is_safe = True
	if ENEMY_WILL_COME_IN != {}:
		if ENEMY_WILL_COME_IN[str(position)] <= time_limit:
			is_safe = False

		adjacent_positions = AdjacentPositions(position)
		if ENEMY_WILL_COME_IN != {}:
			for adj_pos in adjacent_positions:
				if ENEMY_WILL_COME_IN[str(adj_pos)] <= time_limit:
					is_safe = False
					break
	return is_safe


# определить, безопасен ли мой маршрут, т.е. успеет ли его кто-то пересечь; используется просчитанный словарь ENEMY_WILL_COME_IN
def IsRouteSafe(route):
	is_safe = True

	path = route['path']
	time_limit = route['ticks']

	if path is None: # поиск пути закончился неудачей
		is_safe = False
	elif ENEMY_WILL_COME_IN != {}: # путь существует и противники на поле ещё есть
		# проверяем клетки пути и соседние им клетки
		for pos in path:
			is_safe = IsRouteStepSafe(pos, time_limit)
			if not is_safe:
				break

		for pos in PLAYER_ME.trace: # проверяем каждую клетку следа на возможность пересечения соперником
			if ENEMY_WILL_COME_IN[str(pos)] < time_limit:
				is_safe = False
				break

	return is_safe


# попытаться построить безопасный маршрут домой, начиная со смежной мне точки
def GetSafeRouteBackFromAdjPos(target_pos):
	back_route = {'path': None, 'ticks': None}
	
	# фантомно сдвигаемся на смежную клетку
	target_cell = GAME_FIELD[target_pos]

	# запоминаем старые данные клетки, на которую сдвигаемся и переписываем новыми
	old_trace_sign = target_cell.signs['trace']
	target_cell.signs['trace'] = 'i'
	PLAYER_ME.trace.append(target_pos)

	old_direction = PLAYER_ME.direction
	PLAYER_ME.direction = GetCommandFromTo(PLAYER_ME.position, target_pos)

	old_position = PLAYER_ME.position.copy()
	PLAYER_ME.position = target_pos.copy()

	moves_made_before = 1
	back_route = GetRouteToClosest(PLAYER_ME, ['i'], ['territory'], WITH_PRIORITY,
								   moves_made_before, CAN_NOT_CROSS_TRACE) # считаем, как быстро я вернусь домой с соседней клетки

	# откатываем "фантомное" перемещение
	target_cell.signs['trace'] = old_trace_sign
	PLAYER_ME.trace.remove(target_pos)
	PLAYER_ME.direction = old_direction
	PLAYER_ME.position = old_position

	if back_route['path'] is not None: # получили путь домой с клетки
		back_route['path'].insert(0, target_pos) # включим смежную клетку в маршрут
		back_route['ticks'] += (GLOBAL_PARAMS.width // PLAYER_ME.CurrentSpeed()) # и соответственно увеличим время

		# проверим маршрут на безопасность
		if not IsRouteSafe(back_route):
			back_route['path'] = None
			back_route['ticks'] = None
	
	return back_route


# если скоро конец игры, бежим на свою территорию
# получить команду для следования домой кратчайшим маршрутом
def ReturnHomeIfGameEnd():
	cmd = None

	if GAME_FIELD[PLAYER_ME.position].signs['territory'] != 'i': # я нахожусь за пределами своей территории
		ticks_left = (GLOBAL_PARAMS.maxTickCount - GLOBAL_PARAMS.tickNum) # тиков до конца игры
		if ( # пора бежать домой?
			CLOSEST_ROUTE_TO_HOME['path'] is not None and CLOSEST_ROUTE_TO_HOME['path'] != []
			and ticks_left < CLOSEST_ROUTE_TO_HOME['ticks'] + 20  # 20 тиков для подстраховки
		):
			route_first_pos = CLOSEST_ROUTE_TO_HOME['path'][0] # если путь не None, то в нём точно что-то есть, ведь я не на своей территории
			cmd = GetCommandFromTo(PLAYER_ME.position, route_first_pos)

	return cmd


# посмотрим, можно ли безопасно пересечь след противника
# если да, вернёт команду для следования этим маршрутом
def TryToCrossAnyTrace():
	cmd = None

	for player_sign in ANOTHER_PLAYERS:
		moves_made_before = 0
		crossing_route = GetRouteToClosest(PLAYER_ME, [player_sign], ['trace'], WITH_PRIORITY,
										   moves_made_before, CAN_NOT_CROSS_TRACE) # мой путь до следа противника

		arrival_route = GetRouteToClosest(ANOTHER_PLAYERS[player_sign], [player_sign], ['territory'], WITHOUT_PRIORITY,
										  moves_made_before, CAN_NOT_CROSS_TRACE) # путь противника до его территории
		if (
			crossing_route['ticks'] is not None and arrival_route['ticks'] is not None # оба маршрута существуют
			and crossing_route['ticks'] < arrival_route['ticks'] # мой маршрут короче
		):  # нашли такую возможность
			target_pos = crossing_route['path'][0] # клетка, на которую собираемся перейти на этом ходу
			back_route = GetSafeRouteBackFromAdjPos(target_pos) # а сможем ли мы безопасно вернуться с той клетки, на которую переходим?
			if back_route['path'] is not None: # сможем вернуться
				cmd = GetCommandFromTo(PLAYER_ME.position, target_pos)
				break

	return cmd


# попытаться найти безопасный маршрут к бонусу нитро, если он есть на поле
# возвращает команду для следования этим маршрутом
def TryPickUpNitro():
	cmd = None

	moves_made_before = 0
	route_to_nitro = GetRouteToClosest(PLAYER_ME, [], ['nitro'], WITH_PRIORITY,
									   moves_made_before, CAN_NOT_CROSS_TRACE) # ищем безопасный маршрут к бонусу нитро

	if route_to_nitro['path'] is not None: # маршрут существует
		target_pos = route_to_nitro['path'][0] # клетка, на которую собираемся перейти
		back_route = GetSafeRouteBackFromAdjPos(target_pos) # успеем вернутся домой с этой клетки?
		if back_route['path'] is not None: # успеваем
			cmd = GetCommandFromTo(PLAYER_ME.position, target_pos)

	return cmd


# служебный метод - выбор ходов по приоритету; нужен для CommandByMoves
def SubMovesByPriority(moves, priority):
	sub_moves = []
	for elem in moves:
		if elem['priority'] == priority:
			sub_moves.append(elem)
	return sub_moves


# по свофрмированному списку соседних ячеек с приоритетами выбрать оптимальную для перехода
def CommandByMoves(moves):
	cmd = None
	destination = None  # клетка, куда будем двигаться

	# средни не моих клеток, которые являются чей-то территорией, будет выбирать ту, с которой дольше всего возвращаться
	if destination is None:
		sub_moves = SubMovesByPriority(moves, 1)
		arrival_time = None
		for elem in sub_moves:
			if arrival_time is None or elem['ticks'] > arrival_time:
				arrival_time = elem['ticks']
				destination = elem['position']

	# среди не моих клеток, которые пустые, будем выбирать ту, с которой дольше всего возвращаться
	if destination is None:
		sub_moves = SubMovesByPriority(moves, 2)
		arrival_time = None
		for elem in sub_moves:
			if arrival_time is None or elem['ticks'] > arrival_time:
				arrival_time = elem['ticks']
				destination = elem['position']

	# среди клеток моей территории будем выбирать те, которые ближе всего к территории противника
	if destination is None:
		sub_moves = SubMovesByPriority(moves, 3)

		owners_list = []  # список игроков, чью территорию рассматривыаем как не свою
		for sign in ANOTHER_PLAYERS:
			owners_list.append(sign)

		# если противников не осталось, будем двигаться к ближайшей пустой клетке
		search_types = ['territory']
		if owners_list == []:
			search_types = ['empty']

		min_time = None
		for elem in sub_moves:
			target_pos = elem['position']
			target_cell = GAME_FIELD[target_pos]

			old_trace_sign = target_cell.signs['trace']
			target_cell.signs['trace'] = 'i'
			PLAYER_ME.trace.append(target_pos)

			old_direction = PLAYER_ME.direction
			PLAYER_ME.direction = GetCommandFromTo(PLAYER_ME.position, target_pos)

			old_position = PLAYER_ME.position.copy()
			PLAYER_ME.position = target_pos.copy()

			moves_were_made = 1
			route_to_not_my_cell = GetRouteToClosest(PLAYER_ME, owners_list, search_types, WITHOUT_PRIORITY,
													 moves_were_made, CAN_CROSS_TRACE) # посчитали путь до ближайшей не моей клетки

			# откатываем фантомное перемещение
			target_cell.signs['trace'] = old_trace_sign
			PLAYER_ME.trace.remove(target_pos)
			PLAYER_ME.direction = old_direction
			PLAYER_ME.position = old_position

			if route_to_not_my_cell['path'] is not None: # маловероятно, чтобы путь не нашёлся, но всё же
				if min_time is None or route_to_not_my_cell['ticks'] < min_time:
					min_time = route_to_not_my_cell['ticks']
					destination = target_pos

	# в крайнем случае будем двигаться навстречу своему хвосту, что не очень хорошо, но терпимо
	if destination is None:
		sub_moves = SubMovesByPriority(moves, 4)
		arrival_time = None
		for elem in sub_moves:
			if arrival_time is None or elem['ticks'] < arrival_time:  # выбираем клетки, откуда ближе всего возвращаться
				arrival_time = elem['ticks']
				destination = elem['position']

	# совсем в крайнем случае пойдём на клетку с замедлением, это потенциально рушит все рассчёты
	if destination is None:
		sub_moves = SubMovesByPriority(moves, 5)
		# пофиг на все проверки; если оказались в такой ситуации, всё очень плохо, тупо берём первую клетку
		if len(sub_moves) > 0:
			destination = elem['position']

	if destination is not None:
		cmd = GetCommandFromTo(PLAYER_ME.position, destination)

	return cmd


# совсем простая логика на крайний случай
# пытаемся вернуться домой, а если непрокатило, то -
# отойти от противника как можно дальше, оставаясь на своей территории
def ReturnHomeOrRunFromEnemy():
	cmd = None
	destination = None

	if GAME_FIELD[PLAYER_ME.position].signs['territory'] != 'i':  # если мы не на своей территории, то кратчайшим путём возвращаемся домой
		path = CLOSEST_ROUTE_TO_HOME['path']
		if path is not None and path != []:
			destination = path[0]
	else:  # если мы на своей территории, то постараемся как можно дальше отойти от противников, оставаясь на своей территории
		positions_to_move = PositionsToMove(PLAYER_ME.direction, PLAYER_ME.position,
											PLAYER_ME.sign,
											CAN_NOT_CROSS_TRACE)  # соседние ячейки, на которые можем перейти
		my_positions = []  # мои соседние клетки
		for pos in positions_to_move:
			if GAME_FIELD[pos].signs['territory'] == 'i':
				my_positions.append(pos)

		max_min_dist = None
		for pos in my_positions:  # для каждой клетки посчитаем минимальное расстояние до противника
			min_dist = None
			for player_sign in ANOTHER_PLAYERS:
				dist_to_enemy = CalcDistance(pos, ANOTHER_PLAYERS[player_sign].position)
				if min_dist is None or dist_to_enemy < min_dist:
					min_dist = dist_to_enemy
			if max_min_dist is None or min_dist > max_min_dist:
				max_min_dist = min_dist
				destination = pos

		# не получилось остаться на своей территории, придётся осмотреть не свои клетки
		if destination is None:
			not_my_positions = []  # мои соседние клетки
			for pos in positions_to_move:
				if GAME_FIELD[pos].signs['territory'] == 'i':
					not_my_positions.append(pos)

			max_min_dist = None
			for pos in not_my_positions:  # для каждой клетки посчитаем минимальное расстояние до противника, а потом среди них найдём максимум
				min_dist = None
				for player_sign in ANOTHER_PLAYERS:
					dist_to_enemy = CalcDistance(pos, ANOTHER_PLAYERS[player_sign].position)
					if min_dist is None or dist_to_enemy < min_dist:
						min_dist = dist_to_enemy
				if max_min_dist is None or min_dist > max_min_dist:
					max_min_dist = min_dist
					destination = pos

	if destination is not None:
		cmd = GetCommandFromTo(PLAYER_ME.position, destination)

	return cmd


# дополнить вражеские маршруты кратчайшим образом до их территории
def CompleteEnemyTraces():
	for sign in ANOTHER_PLAYERS:
		curr_player = ANOTHER_PLAYERS[sign]
		moves_made_before = 0
		home_route = GetRouteToClosest(curr_player, [sign], ['territory'], WITHOUT_PRIORITY, moves_made_before, CAN_NOT_CROSS_TRACE)
		if home_route['path'] is not None and home_route['path'] != []: # удалось достроить вражеский маршрут и он не пуст
			closest_center = GetClosestCenter(curr_player) # исходную клетку тоже будем считать маршрутом
			if closest_center not in home_route['path']:
				home_route['path'].insert(0, closest_center)

			for pos in home_route['path']: # дополняем следы игроков фантомными данными
				curr_player.trace.append(pos)
				GAME_FIELD[pos].signs['trace'] = sign


# жёский хак - проверяем, существует ли путь от меня до границы игрового поля
# если существует, то меня не закрашивают
# но след противника пересекать нельзя!
def IfExistsRouteToBorder(enemy_sign):
	route_to_border_exists = False

	visited = {} # словарь обработанных клеток

	# обрабатываем начало поиска
	frontier = queue.Queue()
	frontier.put(PLAYER_ME.position)
	visited[str(PLAYER_ME.position)] = True

	while not frontier.empty():
		current_position = frontier.get()
		curr_cell = GAME_FIELD[current_position]
		if curr_cell is None:
			route_to_border_exists = True
			break

		adjacent_positions = AdjacentPositionsWithNone(current_position)
		positions_to_delete = []
		for pos in adjacent_positions:
			cell = GAME_FIELD[pos]
			if cell is not None:
				if (
					cell.signs['trace'] == enemy_sign
					or (
						cell.signs['territory'] == enemy_sign
						and cell.signs['trace'] != 'i'
					)
				):
					positions_to_delete.append(pos)

		able_positions = [pos for pos in adjacent_positions if pos not in positions_to_delete]

		for next_position in able_positions:  # просматриваем соседей
			if str(next_position) not in visited:
				frontier.put(next_position)
				visited[str(next_position)] = True

	return route_to_border_exists


# определить, проходит ли вражеский след по моей территории
def EnemyTraceOnMyTerritory(enemy_sign):
	result = False

	intersection = [value for value in ANOTHER_PLAYERS[enemy_sign].trace if value in PLAYER_ME.territory]
	if len(intersection) > 0:
		result = True

	return result


# проверить, не закрашивают ли меня, и если да, то поступить соответственно
def ProcessMePaintingOver():
	cmd = None

	for enemy_sign in ANOTHER_PLAYERS: # провеяем каждого игрока, не закрашивает ли он меня
		if EnemyTraceOnMyTerritory(enemy_sign) and not IfExistsRouteToBorder(enemy_sign): # МЕНЯ ЗАКРАШИВАЮТ! - не существует маршрута до границы игрового поля
			if GAME_FIELD[PLAYER_ME.position].signs['territory'] != 'i': # я не на своей территории
				# надо домой
				if CLOSEST_ROUTE_TO_HOME['path'] is not None and CLOSEST_ROUTE_TO_HOME['path'] != []:
					cmd = GetCommandFromTo(PLAYER_ME.position, CLOSEST_ROUTE_TO_HOME['path'][0])
			else: # я на своей территории
				# мчимся навстречу следу противника, чтобы он отвернул
				moves_made_before = 0
				rote_to_enemy_trace = GetRouteToClosest(PLAYER_ME, [enemy_sign], ['trace'], WITH_PRIORITY,
														moves_made_before, CAN_NOT_CROSS_TRACE)
				if rote_to_enemy_trace['path'] is not None and rote_to_enemy_trace['path'] != []:
					cmd = GetCommandFromTo(PLAYER_ME.position, rote_to_enemy_trace['path'][0])
			break

	return cmd


'''
===ОПИСАНИЕ СТРАТЕГИИ===
1. Возвращаемся домой, если конец игры.
   Вычисляем кратчайший безопасный путь до своей территории. Если не успеваем его пройти к моменту за 20 тиков до конца игры, рвём когти домой.

2. Пытаемся пересечь чужой след.
   Считаем своё время до пересечения вражеского следа. Считаем вражеское время до возвращения домой. Если наше время меньше, стремимся убить противника.
   Но делаем всё МАКСИМАЛЬНО безопасно.

3. Пытаемся взять нитро.
   Нитро - это хорошо. Будем двигаться в его сторону, но тоже безопасно. Чаще всего это движение будет превращаться в обычный захват территории.

4. Перебираем доступные для перехода ячейки, чтобы выбрать оптимальный ход. Всё делаем МАКСИМАЛЬНО безопасно.
   Клетка для перехода считается безопасной, если я окажусь на ней раньше, чем противник окажется на ней или лобой соседней клетке.
   При построении безопасных маршрутов в будущее используются те же критерии.
   Каждой из соседних клекок присвоим приоритет. Чем выше приоритет - тем хуже клетка.
   5 - Клетки с замедлением. На них переходмим в крайнем случае, т.к. взятие  замедление за границами своей территории
       может порушить все расчёты. Изо всех сил не берём.
   4 - Клетки не моей территории, но ведущие "навстречу" моему собственному следу.
       Переход на такие клетки ведёт к "закручиванию" маршрута и в целом не самым выгодным ходам, что нам не особо надо.
   3 - Клетки моей территории. Тут всё просто - это лучше, чем закручивать свой путь или хватать замедление.
   2 - Клетки не моей территории, ничейные. Переходим приоритетно на такие клетки, чтобы захватываемая область увеличивалась.
   1 - Клетки не моей территории, но других игроков. Очень дорогие и потому "вкусные". Переходим на них в первую очередь.

5. Если никакая команда не была выбрана, всё плохо. Где-то мы проебались. Скорее всего, строгие ограничения на безопасность клеток загнали нас в угол.
   Что делать? Если я на не на своей территории, то кратчайшим путём рву когти домой. Есть шанс, что противник не сагрится.
   Если я на своей территории, то постараюсь отойти как можно дальше от противника - дай дорогу дураку.
      При этом постараюсь остаться на своей территории, если можно.

6. Если команда всё ещё не была вычислена, всё совсем плохо. Даём рандомную команду и молимся Ктулху (бесполезно).

===СДЕЛАТЬ===
1. Кратчайшим образом достраивать пути противников, находящихся на моей территории.
   В первую очередь это поможет всегда возвращаться в одну компоненту связности - в ту, из которой мы стартовали.
   Здесь же надо подумать, как закрашивать территорию после завершения призрачных траекторий противников.
   Есть сценарии, когда только симуляция финальной закраски может предупредить об опасности.

2. Надо бы сделать какую-то обработку пилы. Например, не стоять на одной линии с пилой и противником.

3. Наверное, есть смысл двигаться в сторону не ближайшей чей-то ячейки, а в сторну игрока с наибольшим количеством очков.

===ПРИОРИТЕТЫ ХОДОВ===
1 - территория другого игрока, не навстречу моему следу
2 - ничья территория, не навстречу моему следу
3 - моя территория
4 - клетки навстречу моему собственному следу
5 - клетки с бонусом "замедление"
'''

### ТОЧКА ВХОДА В ПРИЛОЖЕНИЕ ###

GLOBAL_PARAMS = GlobalParams()
PLAYER_ME = Player('i')
ANOTHER_PLAYERS = {}
GAME_FIELD = GameField()
ENEMY_WILL_COME_IN = {}
CLOSEST_ROUTE_TO_HOME = {'path': None, 'ticks': None}

WITH_PRIORITY = True
WITHOUT_PRIORITY = False
CAN_CROSS_TRACE = True
CAN_NOT_CROSS_TRACE = False

DEBUG_MSG = ''

while True:
	input_str = input()
	input_type_str = ParseInput(input_str)

	if input_type_str == 'tick':
		cmd = None
		ENEMY_WILL_COME_IN = CalcEnemyWillComeIn()
		CLOSEST_ROUTE_TO_HOME = GetRouteToClosest(PLAYER_ME, ['i'], ['territory'], WITH_PRIORITY, 0, CAN_NOT_CROSS_TRACE)

		# перед концом игры рвём когти домой
		if cmd is None:
			cmd = ReturnHomeIfGameEnd()

		# рассчитываем команду для пересечения следа противнкиа, если есть возможность
		# не применяем, а запоминаем
		cross_trace_cmd = TryToCrossAnyTrace()

		# рассчитываем команду для взятия нитро
		# не применяем, а запоминаем
		nitro_cmd = TryPickUpNitro()

		# рассчитываем команду, для крайнего случая, если всё остальное не сработает; например, если нас загнали в угол
		# не применяем, просто запомнили; применим в самом конце
		last_cmd = ReturnHomeOrRunFromEnemy()

		# дальше исходное состояние поля разрушается нашими "домыслами" в будущее
		CompleteEnemyTraces()  # дополняем вражеские маршруты до их территории

		# проверяем, не закрашивают ли нас, и если да, то поступаем соответсвенно
		if cmd is None:
			cmd = ProcessMePaintingOver()

		# ищем возможность пересечь чужой след
		if cmd is None:
			cmd = cross_trace_cmd

		# пытаемся взять нитро
		if cmd is None:
			cmd = nitro_cmd

		# если всё ещё нет команды, просмотрим соседние клетки и подумем, куда выгодней всего переместиться
		if cmd is None:
			positions_to_move = PositionsToMove(PLAYER_ME.direction, PLAYER_ME.position,
												PLAYER_ME.sign, CAN_NOT_CROSS_TRACE) # соседние ячейки, на которые можем перейти
			moves = [] # список ходов с соответствующими приоритетами

			for target_pos in positions_to_move: # проверяем каждую клетку, куда можно перейти
				target_cell = GAME_FIELD[target_pos]

				if target_cell.signs['bonus'] == 's': # это клетка с замедлением, пойдём на неё только в крайнем случае
					moves.append({'priority': 5, 'ticks': None, 'position': target_pos})
				elif target_cell.signs['territory'] == 'i': # если клетка - моя территория, надо проверить, безопасна ли она для перехода
					if IsRouteStepSafe(target_pos, GLOBAL_PARAMS.width // PLAYER_ME.CurrentSpeed()):
						moves.append({'priority': 3, 'ticks':  None, 'position': target_pos})
				else: # не моя территория, надо смотреть, успею ли вернуться на свою территорию
					back_route = GetSafeRouteBackFromAdjPos(target_pos)
					if back_route['path'] is not None: # существует безопасный путь домой со смежной клетки
						if TowardsMyTrace(PLAYER_ME.position, target_pos): # движение в сторону своего следа считаем нежелательным
							moves.append({'priority': 4, 'ticks': back_route['ticks'], 'position': target_pos})
						else:
							if target_cell.signs['territory'] is not None: # чужие клетки более ценны, чем пустые
								moves.append({'priority': 1, 'ticks':  back_route['ticks'], 'position': target_pos})
							else:
								moves.append({'priority': 2, 'ticks': back_route['ticks'], 'position': target_pos})
			# for target_pos in positions_to_move:
			cmd = CommandByMoves(moves) # из всех вариантов переходов выберем самый оптимальный по приоритету

		# всё плохо, применяем рассчитанную ранее команду на крайний случай
		if cmd is None:
			cmd = last_cmd

		# совсем в крайнем случае выполняем рандомную команду, но это прям ваще край
		if cmd is None:
			DEBUG_MSG += "RANDOM!"
			cmd = GetRandomCommand(PLAYER_ME)

		DEBUG_MSG += ' , cmd = {0}'.format(cmd)
		print(json.dumps({"command": cmd, 'debug': DEBUG_MSG}))

		GAME_FIELD.ClearField()
		CLOSEST_ROUTE_TO_HOME = {'path': None, 'ticks': None}
		DEBUG_MSG = ''
	# if input_type_str == 'tick':