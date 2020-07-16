import requests, json
import itertools
import copy
import time
import csv
import random
from math import ceil
from tempfile import NamedTemporaryFile
from django.conf import settings
from .models import *
import cProfile

class _RealAuto:
    _counter = 0 #внутренний уникальный счетчик объектов

    def __init__(self, capacity, reis_max, driver_limit, start_time=0, start_time_free=False, name='',):
        self.name = name
        self.capacity = capacity
        self.reis_max = reis_max
        self.start_time = start_time #в секундах с полночи время прибытия на погрузку
        self.start_time_free = start_time_free # Плавающее время старта (не задано)
        self.driver_limit = driver_limit
        _RealAuto._counter += 1
        self.num = _RealAuto._counter

    def __str__(self):
        return f"{self.num} {self.name}"

    @staticmethod
    def clear_counter(): #очистка внутреннего уникального номера
        _RealAuto._counter = 0


class _DeliveryDot: #Точка доставки
    def __init__(self, client_name, client_address, quantity, window_from, window_to, obj, latitude, longtitude, process_time=(10*60), priority=0):
        self.client_name = client_name
        self.client_address = client_address
        self.quantity = quantity
        self.window_from = window_from
        self.window_to = window_to
        self.process_time = process_time
        self.priority = priority
        self.latitude = latitude
        self.longtitude = longtitude
        self.obj = obj
        self.matrix_idx = -1
        self.idx = -1


class _StoreDot: #Точка склада
    def __init__(self, obj):
        self.obj = obj #Ссылка на исходный объект в БД
        self.matrix_idx = -1


class _CurrentAuto:
    def __init__(self, real_auto, current_reis=1):
        self.real_auto = real_auto
        self.current_reis = current_reis
        self.current_time = 0 #Текущее время автомобиля (В секундах с полуночи)
        self.set_default()

    def __str__(self):
        return f"{self.current_reis} {self.real_auto.num}"

    def set_default(self):
        if self.real_auto.start_time_free:
            self.real_auto.start_time = 0
        self.current_time = self.real_auto.start_time


class _CurrentRoute:
    def __init__(self, dot, auto_num, start_time, load_time, reis_num = 1, with_return=False):
        self.dots = [dot]
        self.auto_num = auto_num
        self.reis_num = reis_num
        self.start_time = start_time #время начала рейса (становления на погрузку) в секундах с полуночи
        self.load_time = load_time #Время погрузки на складе
        self.end_time = start_time #Время окончания маршрута (прибытия на склад) в секундах с полуночи
        self.wait_time_total = 0 #общее время ожидания (до окна приемки)
        self.with_return = with_return #Маршрут с возвратом на склад

    def get_quantity(self, delivery_dots):
        quantity = 0
        for dot in self.dots:
            quantity += delivery_dots[dot - 1].quantity
        return quantity


def _fill_real_autos(auto_list):
    _RealAuto.clear_counter()  # очищаем внутренний счетчик машин перед инициализацией нового списка
    result_auto_list = []
    for single_auto in auto_list:
        result_auto_list.append(_RealAuto(
            name=single_auto['name'],
            capacity=single_auto['capacity'],
            reis_max=single_auto['reis_max'],
            start_time=single_auto['start_time'],
            start_time_free=single_auto['start_time_free'],
            driver_limit=single_auto['driver_limit'],
        ))
    return result_auto_list


def _fill_store_dots(store_object):
    store_dot = _StoreDot(obj=store_object)
    return store_dot


def _fill_delivery_dots(delivery_dots_list):
    delivery_dots_result = []
    for single_dd in delivery_dots_list:
        delivery_dots_result.append(_DeliveryDot(client_name=single_dd['client_name'],
                                                 client_address=single_dd['client_address'],
                                                 quantity=single_dd['quantity'],
                                                 priority=single_dd['priority'],
                                                 window_from=single_dd['window_from'],
                                                 window_to=single_dd['window_to'],
                                                 process_time=single_dd['process_time'],
                                                 obj=single_dd['client_object'],
                                                 latitude=single_dd['latitude'],
                                                 longtitude=single_dd['longtitude'],
                                                 ))
    return delivery_dots_result


def _get_distance_matrix(store_dot, delivery_dots): #Запрос на OSRM
    osrm_route_service = f"{settings.OSRM_SERVER_URL}/table/v1/driving/"

    dots = [] #Список координат, которые будут переданы OSRM сервису
    dots.append(f'{store_dot.obj.longtitude},{store_dot.obj.latitude}')
    store_dot.matrix_idx = 0

    idx = 0
    while idx < len(delivery_dots):
        dots.append(f'{delivery_dots[idx].longtitude},{delivery_dots[idx].latitude}')
        delivery_dots[idx].idx = idx
        delivery_dots[idx].matrix_idx = idx + 1 #индекс +1 из-за того, что 0 индекс в матрице расстояний и времени - склад
        idx += 1

    address = osrm_route_service + ';'.join(dots)
    try:
        r = requests.get(address, params={'annotations': 'duration,distance'}, timeout=None)
    except Exception as e:
        raise ValueError(f"Ошибка запроса расстояний: {str(e)}")
    data = json.loads(r.text)
    if data['code'] == "Ok":
        distance_matrix = data["distances"]
        times_matrix = data["durations"]
    else:
        raise ValueError(f"Ошибка запроса расстояний: {data['message']}")

    #Создаем матрицу выигрышей, сортируем по возрастанию матрицу времени или расстояний и записываем туда id элемента
    matrix_to_sort = times_matrix #Выигрыш определяем по времени
    win_matrix = []
    for idx, single_list in enumerate(matrix_to_sort):
        win_arr = {i : single_list[i] for i in range(0, len(single_list))} #Перевод из списка в массив, где ключ - индекс списка, значение - элемент списка
        win_arr = [idx for idx, val in sorted(win_arr.items(), key=lambda x: x[1]) if val is not None and idx > 0] # Сортировка времени пути по возрастанию, запись только id элемента
        win_matrix.append(win_arr)

    return win_matrix, distance_matrix, times_matrix, store_dot, delivery_dots


def _get_trip_time(val): #Время в минутах из точки i в точку j
    result = int(ceil(val / 60)) * 60 #время округляем до целой минуты вверх
    return result


def _combi_idx(single_combination): # Получить индекс текущей комбинации авто (массив из объектов CurrentAuto)
    # Индекс имеет вид (n,m), где n - номер рейса, m - номер атво
    idx = [(auto.current_reis, auto.real_auto.num) for auto in single_combination]
    idx = tuple(idx)
    return idx


def _find_max_win(win_matrix, ignore_list, dot_from=0): #ф-ция поиска максимального выигрыша, со списком игнорируемых элементов
    #параметр dot_from - ищем максимальный выигрыш от заданной точки до всех других (т.е. минимальное значение (километров\секунд))

    for idx in win_matrix[dot_from]:
        if idx == dot_from: continue
        if idx in ignore_list: continue

        return idx #Список отсортирован по возрастанию, так что нам достаточно взять первый, удовлетворяющий по условиям

    return None


# Получение экземпляров CurrentAuto из RealAuto (авто, поделенные на рейсы)
def _algo_get_current_auto_list(auto):
    return [_CurrentAuto(real_auto=auto, current_reis=reis_num) for reis_num in range(1, auto.reis_max + 1)]


# Получение списка "полных" комбинаций, пригодных для расчета маршрута
def _algo_auto_get_full_combinations(auto_list, base_combinations, high_accuracy, auto_min):
    full_combinations_list = []

    max_combinations = 2 # Сколько строить комбинаций для случайного распределения
    max_autos = 5 # Сколько нерассчитанных авто использовать в маршруте за раз (только для случая неточного маршрута)
    for base_comb in base_combinations:
        # Подготовка списка авто, с которым будем делать комбинации (незадействованные в базовом маршруте)
        auto_list_for_combi = []
        for auto in auto_list:
            try:  # Поиск авто в уже построенном базовом маршруте single_combination
                if auto_min: # В случае минимизации транспорта поиск идет по RealAuto
                    next(x for x in base_comb if x.real_auto.num == auto.num)
                else: # В случае обычного расчета поиск идет уже по CurrentAuto
                    next(x for x in base_comb if x.real_auto.num == auto.real_auto.num
                         and x.current_reis == auto.current_reis)
            except StopIteration:  # Если авто еще не использовалось в маршруте
                auto_list_for_combi.append(auto)
        # Если осталось много авто для распределения в маршрут, необходимо выбрать только несколько комбинаций
        if len(auto_list_for_combi) > 2: # Расставляем комбинации случайным образом
            if high_accuracy:
                combi_len = len(auto_list_for_combi)
            else:
                combi_len = min(len(auto_list_for_combi), max_autos)
            for _ in range(max_combinations):
                tmp_combination = random.sample(auto_list_for_combi, combi_len)
                ca_list = []
                if auto_min:
                    for auto in tmp_combination: # Простановка CurrentAuto экземпляров (авто поделенные на рейсы)
                        ca_list += _algo_get_current_auto_list(auto)
                else:
                    ca_list = random.sample(auto_list_for_combi, combi_len)
                full_combinations_list.append({
                    'base_combination': base_comb,
                    'full_combination': copy.deepcopy(base_comb) + ca_list,
                })
        else: # Берем все доступные комбинации
            tmp_combinations = list(itertools.permutations(auto_list_for_combi))
            for single_combination in tmp_combinations:
                ca_list = []
                if auto_min:
                    for auto in single_combination:  # Простановка CurrentAuto экземпляров (авто поделенные на рейсы)
                        ca_list += _algo_get_current_auto_list(auto)
                else:
                    ca_list = list(single_combination)
                full_combinations_list.append({
                    'base_combination': base_comb,
                    'full_combination': copy.deepcopy(base_comb) + ca_list,
                })

    if not full_combinations_list: #Если больше нечего комбинировать
        for base_combination in base_combinations:
            full_combinations_list.append({
                'base_combination': base_combination,
                'full_combination': copy.deepcopy(base_combination),
            })

    return copy.deepcopy(full_combinations_list)


# Получаем список базовых комбинаций
def _algo_auto_get_base_combinations(auto_list, combination_list, auto_min):
    # auto_list - список авто, по которому надо работать
    # combination_list - комбинация авто, которые уже участвуют в маршруте
    # auto_min - режим минимизации транспорта (не делить по рейсам)

    base_combinations_list = []
    if auto_min: # Построение списка авто для режима минимизации кол-ва авто
        for auto in auto_list: # По экземлярам RealAuto
            try: #Поиск авто в уже построенном базовом маршруте combination_list
                next(x for x in combination_list if x.real_auto.num == auto.num)
            except StopIteration: # Если авто еще не использовалось в маршруте - создаем с ним маршрут
                single_combination = copy.deepcopy(combination_list)
                # Получаем список экземпляров CurrentAuto (авто, разделенные по рейсам)
                ca_list = _algo_get_current_auto_list(auto)
                single_combination += ca_list
                base_combinations_list.append(single_combination)
    else: # Режим "обычного" расчета (с последовательным распределением ТТ по авто и рейсам)
        for cur_auto in auto_list: # По экземплярам CurrentAuto
            try:  # Поиск авто в уже построенном базовом маршруте combination_list
                next(x for x in combination_list if x.real_auto.num == cur_auto.real_auto.num
                                                and x.current_reis == cur_auto.current_reis)
            except StopIteration:  # Если авто еще не использовалось в маршруте - создаем с ним маршрут
                single_combination = copy.deepcopy(combination_list)
                single_combination.append(copy.deepcopy(cur_auto))
                base_combinations_list.append(single_combination)

    return copy.deepcopy(base_combinations_list)


# Создание списка статических авто, согласно режима минимизация транспорта
def _algo_get_auto_reis(real_autos, auto_min):
    if not len(real_autos):
        return []
    if auto_min: # Для режима минимизации транспорта список генерируется при создании комбинации авто
        return [real_autos]
    # Создание списка машин, разделенных по рейсам для "обычного" режима
    auto_reis = []
    reis_num = 0
    while True:
        reis_num += 1
        reis_list = []
        for auto in real_autos:
            if auto.reis_max < reis_num:
                continue
            reis_list.append(_CurrentAuto(real_auto=auto, current_reis=reis_num))
        if len(reis_list) == 0:
            break #Машин с данным номером рейса не нашлось, выходим
        auto_reis.append(reis_list)
    return auto_reis


def _algo_checks_required(single_auto, route, delivery_dots): #обязательные(фундаментальные) проверки, котоыре ни при каких условиях нельзя нарушать
    #route - обьект, который будет сохранен если условия ниже вернут true, т.е. это уже маршрут с ДОБАВЛЕННОЙ точкой

    #проверка на вместимость автомобиля на маршруте
    route_quantity = route.get_quantity(delivery_dots)
    if single_auto.real_auto.capacity < route_quantity: return False, 0

    return True, route_quantity


def _algo_checks_window(single_auto, deliv_dot, trip_time, trip_time_st, early_arrival=0, lately_arrival=0): #проверки на окна доставки и временные ограничения
    #early_arrival - на сколько можно приехать раньше (сколько водитель может подождать перед приемкой, условно говоря), в секундах
    #lately_arrival - на сколько можно задержаться, но все таки приехать в магазин на разгрузку (не работает для магазинов с приоритетом >= 5), в секундах
    #route - обьект, который будет сохранен если условия ниже вернут true, т.е. это уже маршрут с ДОБАВЛЕННОЙ точкой
    #trip_time_st - время в пути от добавляемой точки до склада

    is_early_arrival = False # Флаг слишком раннего приезда (но пройдены все остальные проверки)

    #Расчет времени прибытия в точку
    if deliv_dot.priority >= 5: lately_arrival = 0 #Нельзя опаздывать в магазины с приоритетом >= 5
    arrival_time = single_auto.current_time + trip_time
    # Сколько нужно подождать водителю, чтобы заехать на данную точку
    wait_time = deliv_dot.window_from - arrival_time
    if wait_time < 0: wait_time = 0

    #Проверка окон доставки
    if deliv_dot.window_to > 0:
        if arrival_time - lately_arrival > deliv_dot.window_to:
            # Опоздание
            return False, wait_time, is_early_arrival
    if deliv_dot.window_from > 0:
        if arrival_time + early_arrival < deliv_dot.window_from:
            # Слишком ранний приезд
            is_early_arrival = True
            return False, wait_time, is_early_arrival

    #Проверка ограничения смены водителя
    if single_auto.current_time + wait_time + trip_time + trip_time_st + deliv_dot.process_time - single_auto.real_auto.start_time > single_auto.real_auto.driver_limit:
        return False, wait_time, is_early_arrival

    return True, wait_time, is_early_arrival


def _algo_get_ignore_list(current_routes): #получаем точки, которые уже обработаны
    ignore_list = set()
    for route in current_routes:
        ignore_list.update(route.dots)
    return ignore_list


def _algo_get_stat(delivery_dots, win_matrix, current_routes, single_combination): #получаем статистику
    stat_priority_bad = 0 #Нераспределенных приоритетных магазинов
    stat_regular_bad = 0 #Нераспределенных обычных магазинов
    stat_autos = 0 #Кол-во задействованного транспорта
    stat_reis = 0 #Кол-во рейсов
    stat_costs = 0 #Общие затраты (по времени)

    processed_dots = _algo_get_ignore_list(current_routes) #Получаем обработанные точки
    for deliv_dot in delivery_dots:
        if deliv_dot.matrix_idx in processed_dots: continue
        if deliv_dot.priority >= 5:
            stat_priority_bad += 1
        else:
            stat_regular_bad += 1

    for route in current_routes:
        if len(route.dots) <= 0: continue

        stat_reis += 1
        if route.reis_num == 1: #Полагаем, что первый рейс всегда означает новую машину
            stat_autos += 1

    #Подсчет общих затрат по времени
    # заполнение таблицы с соответствием авто - время начала\окончания работы авто
    auto_start_end_times = {}
    for single_auto in single_combination:
        try:
            route = next(x for x in current_routes if x.auto_num == single_auto.real_auto.num
                           and x.reis_num == single_auto.current_reis)
        except: #Маршрута нет, времени окончания соотв. тоже, переходим к следующему рейсу
            continue
        # Выбираем максимальное время окончания маршрута для каждой машины, это и будет временем окончания работы водителя (авто)
        try: #Если уже добавляли для данного авто время и оно больше чем текущее - пропускаем
            if auto_start_end_times[single_auto.real_auto.num]['end_time'] > route.end_time:
                continue
        except KeyError: #Для данного авто еще не добавляли время
            pass
        auto_start_end_times[single_auto.real_auto.num] = {
            'start_time': single_auto.real_auto.start_time,
            'end_time': route.end_time
        }
    for key, val in auto_start_end_times.items():
        stat_costs += val['end_time'] - val['start_time']

    route_stat = {
        'stat_priority_bad': stat_priority_bad,
        'stat_regular_bad': stat_regular_bad,
        'stat_autos': stat_autos,
        'stat_reis': stat_reis,
        'stat_costs': stat_costs,
    }
    return route_stat


# Считаем статистику маршрута, сравниваем с лучшим результатом и обновляем его при необходимости
def _algo_main_best_calc_compare(best_calc, current_routes, single_combination, delivery_dots, dots_process_time, win_matrix):
    route_stat = _algo_get_stat(
        delivery_dots,
        win_matrix,
        current_routes,
        single_combination,
    )

    keys = ('stat_priority_bad', 'stat_regular_bad', 'stat_autos', 'stat_reis', 'stat_costs') # по чем находить лучший маршрут, по очереди
    best = False
    if len(best_calc) == 0:
        best = True
    else:
        for key in keys:
            if best_calc[key] > route_stat[key]:
                best = True
            elif best_calc[key] == route_stat[key]:
                continue
            break
    if best:  # Запись лучшего расчета
        best_calc = {
            'stat_priority_bad': route_stat['stat_priority_bad'],
            'stat_regular_bad': route_stat['stat_regular_bad'],
            'stat_autos': route_stat['stat_autos'],
            'stat_reis': route_stat['stat_reis'],
            'stat_costs': route_stat['stat_costs'],
            'current_routes': current_routes,
            'dots_process_time': dots_process_time,
        }
    return best, best_calc


def _algo_main_get_single_route(auto, current_routes, delivery_dots, dots_process_time, current_load_time, max_load_time, params, prev_combination, win_matrix, times_matrix, predefined_win_dot):
    #Копирование потенциально-изменяемых объектов
    auto = copy.deepcopy(auto)
    dots_process_time = list(dots_process_time)

    # Подготовка возвращаемых объектов
    calculated_route = None
    # Отмена добавления последней точки в маршрут (вместо копирования всего маршрута)
    def _undo_calc_route(calculated_route):
        if len(calculated_route.dots) > 1:
            del calculated_route.dots[-1]
        else:
            calculated_route = None
        return calculated_route
    unsuccessfull_load = False # Флаг неуспешной погрузки (не хватило отведенного времени загрузки на следующую ТТ)
    first_early_dot = None  # Первая точка - кандидат на посещение, если вдруг будет перенос времени старта маршрута
    # Для определение первой точки
    first_early_dot_trip = None
    first_early_dot_window = None

    # Если начались следюующие рейсы - добавить ко всем последующим время окончания предыдущих + время из последней точки до склада
    if auto.current_reis > 1:
        try:
            prev_auto = next(x for x in prev_combination if x.real_auto.num == auto.real_auto.num
                             and x.current_reis == auto.current_reis - 1)
            prev_reis = next(x for x in current_routes if x.auto_num == auto.real_auto.num
                             and x.reis_num == auto.current_reis - 1)
            new_time = prev_auto.current_time
            if not params['with_return']:  # Если маршрут без возврата - к предыдущему времени машины не было прибавлено время возврата на склад, но при построении сл. рейса оно нам нужно - добавим
                new_time += _get_trip_time(times_matrix[prev_reis.dots[-1]][0])
            if new_time > auto.current_time:
                auto.current_time = new_time
            if auto.real_auto.start_time_free: # Выставляем время старта рейса (из предыдущей найденной машины)
                auto.real_auto.start_time = prev_auto.real_auto.start_time
        except StopIteration: #Если не найдена машина или рейс, значит машина не подходит в принципе, выходим из расчета
            return calculated_route, auto, dots_process_time, unsuccessfull_load, first_early_dot
    # Для нового маршрута прибавляем ко времени автомобиля время на погрузку
    auto.current_time += current_load_time

    # Поиск первой точки маршрута на основе максимального выигрыша по времени
    ignore_list = set() # точки, содержащиеся в уже построенном маршруте, в матрице выигрышей не участвуют - исключать на момент старта расчета нечего
    # окна доставки
    early_arrival = 0  # на сколько можно приехать раньше и подождать окна приемки
    lately_arrival = 0  # на сколько можно опоздать
    # Время обработки магазина
    deliv_dot_same_coords = False  # Режим "Одинаковые координаты" (2 или более магазинов подряд находятся в 1 точке)
    process_time_all = 0  # Общее время обработки повторяющихся (в 1 координате) магазинов
    process_time_all_count = 0  # Количество таких магазинов (в 1 коорд.)

    full_vehicle = True  # Полная машина (после добавления последней точки ни разу не прошли фундаментальную проверку)
    full_vehicle_repeat = False  # Перезапуск цикла для проверки на нестрогие условия окон доставки (при неполностью загруженной машине)
    while True:  # Цикл для перепроверки нестрогих окон доставки (повтор в случае неполного авто) (достраивает маршрут, не начиная заново)
        while True:  # Цикл по всем точкам для маршрута
            end_dot = 0  # Конечная точка текущего маршрута
            if calculated_route is not None:
                end_dot = calculated_route.dots[-1]

            if predefined_win_dot is not None:
                dot_to = predefined_win_dot
                predefined_win_dot = None
            else:
                dot_to = _find_max_win(win_matrix=win_matrix, ignore_list=ignore_list, dot_from=end_dot)
            if dot_to is None:
                break  # точки кончились

            if calculated_route is not None:
                calculated_route.dots.append(dot_to)
            else:
                calculated_route = _CurrentRoute(
                    dot_to,
                    auto_num=auto.real_auto.num,
                    start_time=auto.current_time - current_load_time, #время приезда на склад, без загрузки
                    load_time=current_load_time,
                    reis_num=auto.current_reis,
                    with_return=params['with_return'],
                )

            deliv_dot = delivery_dots[dot_to - 1]
            if len(calculated_route.dots) > 1:
                deliv_dot_prev = delivery_dots[end_dot - 1]
            else:
                deliv_dot_prev = None
            trip_time = _get_trip_time(times_matrix[end_dot][dot_to])  # время поездки от последней точки в маршруте до добавляемой
            trip_time_extended = times_matrix[end_dot][dot_to]

            "Фундаментальные проверки"
            # Проверка, является ли точка начала маршрута корректной для нас (хватит ли емкости машины загрузиться)
            response, route_quantity = _algo_checks_required(auto, calculated_route, delivery_dots)
            if not response:
                ignore_list.add(dot_to)
                calculated_route = _undo_calc_route(calculated_route)
                continue
            full_vehicle = False  # фундмаентальную проверку прошли, очевидно в машину еще может влезть новый товар

            "Проверка окон доставки и временных ограничений"
            trip_time_st = _get_trip_time(times_matrix[dot_to][0])
            response, wait_time, is_early_arrival = _algo_checks_window(auto, deliv_dot,
                                                      trip_time, trip_time_st, early_arrival=early_arrival,
                                                      lately_arrival=lately_arrival)
            if not response:
                ignore_list.add(dot_to)
                calculated_route = _undo_calc_route(calculated_route)
                if is_early_arrival:
                    # Запись точки - кандидата на посещение при переносе времени маршрута (на самый ранний привоз из возможных)
                    if first_early_dot is None or (
                            first_early_dot_window > deliv_dot.window_from or (
                                first_early_dot_window + early_arrival >= deliv_dot.window_from and
                                first_early_dot_trip < trip_time_extended
                            )
                    ):
                        # Максимальное время поездки и минимальное ожидание из возможных (для самого раннего приезда в магазин)
                        first_early_dot = dot_to
                        first_early_dot_trip = trip_time_extended
                        first_early_dot_window = deliv_dot.window_from
                continue

            "Нахождение времени выгрузки"
            process_time = deliv_dot.process_time
            if deliv_dot_prev is not None and deliv_dot.latitude == deliv_dot_prev.latitude and \
                    deliv_dot.longtitude == deliv_dot_prev.longtitude:
                # одинаковые координаты
                if not deliv_dot_same_coords:  # это - первый магазин с повтором (до него не было повтора координат)
                    deliv_dot_same_coords = True
                    process_time_all = dots_process_time[deliv_dot_prev.idx]
                    process_time_all_count = 1
                    auto.current_time -= dots_process_time[deliv_dot_prev.idx]  # время обработки предыдущей точки убираем (т.к. она повторяющаяся и будет обработана в конце)
                    dots_process_time[deliv_dot_prev.idx] = 0
                process_time_all += dots_process_time[deliv_dot.idx]
                process_time_all_count += 1
                dots_process_time[deliv_dot.idx] = 0
                process_time = 0  # пока время обработки к текущему маршруту не прибавляем
            elif deliv_dot_same_coords:  # Координаты повторялись, но перестали (текущий магазин уже по другим координатам), необходимо рассчитать и прибавить общее время обработки
                process_time_all = int(round(process_time_all / process_time_all_count))
                auto.current_time += process_time_all
                dots_process_time[deliv_dot_prev.idx] = process_time_all
                deliv_dot_same_coords = False

            "Действия после проверки"
            auto.current_time += trip_time + process_time + wait_time
            # Проверка попадания со временем погрузки
            result_load_time = route_quantity * 0.8 * 60 #по 0.8 минут на погрузку 1 лотка, но не больше max_load_time
            if result_load_time > max_load_time: result_load_time = max_load_time
            if result_load_time > current_load_time:
                #Дальнейший расчет невозможен, выходим с возведением флага неуспешной погрузки
                unsuccessfull_load = True
                return calculated_route, auto, dots_process_time, unsuccessfull_load, first_early_dot
            # перестраиваем ignore_list от уже имеющихся точек в маршруте
            ignore_list = _algo_get_ignore_list([calculated_route])
            # добавляем точку к маршруту
            calculated_route.wait_time_total += wait_time
            # Выставляем флаг полного авто, он скинется в False если получится пройти фундаментальную проверку хотя бы раз
            full_vehicle = True

        #  После посещения всех магазинов по условию (для одной машины!), если машина еще не полна - прогоним цикл по магазинам,
        #  сделав окно доставки нестрогим (+- несколько минут)
        if not full_vehicle and not full_vehicle_repeat:
            early_arrival = params['early_arrival']
            lately_arrival = params['lately_arrival']
            full_vehicle_repeat = True
            if calculated_route is None:
                ignore_list = set()
            else:
                ignore_list = _algo_get_ignore_list([calculated_route])
            continue

        break

    # Доп. обработка времени разгрузки в последнем магазине маршрута
    if deliv_dot_same_coords:
        deliv_dot_prev = delivery_dots[calculated_route.dots[-1] - 1]
        process_time_all = process_time_all / process_time_all_count
        auto.current_time += process_time_all
        dots_process_time[deliv_dot_prev.idx] = process_time_all

    # Вывод маршрута и всех изменений для авто
    return calculated_route, auto, dots_process_time, unsuccessfull_load, first_early_dot


# Построение маршрута для одной комбинации автомобиля
def _algo_main_single_combination_calc(cache, single_combination, delivery_dots, dots_process_time, win_matrix, times_matrix, params):
    #Поиск маршрута (или его части) в кэше уже рассчитанных маршрутов
    prev_combination = copy.deepcopy(single_combination)
    while True:
        try:
            cached_calc = cache[_combi_idx(prev_combination)]
            prev_routes = cached_calc['current_routes']
            prev_combination = cached_calc['single_combination']
            dots_process_time = cached_calc['dots_process_time']
            # Если в кеше найден полный маршрут - отдадим его без дополнительного расчета
            if len(prev_combination) == len(single_combination):
                return prev_routes, prev_combination, dots_process_time
            break
        except KeyError: #В кэше нет текущего маршрута
            if len(prev_combination) == 1:
                prev_combination = []
                prev_routes = []
                break #В кэше ничего нет, считаем с нуля
            prev_combination = prev_combination[:-1]

    # Копирование потенциально-изменяемых объектов
    single_combination = copy.deepcopy(single_combination[len(prev_combination):])
    cached_combination = copy.deepcopy(prev_combination)
    prev_combination = copy.deepcopy(prev_combination)
    prev_routes = copy.deepcopy(prev_routes)
    dots_process_time = list(dots_process_time)
    win_matrix = list(win_matrix)

    #Начальные параметры
    start_load_time = 5 * 60 #Начальное время погрузки
    step_load_time = 5 * 60 #Шаг прибавления времени погрузки в алгоритме
    max_load_time = 2 * 60 * 60 #Максимальное время погрузки для рейса

    current_routes = prev_routes  # Построенные маршруты
    for auto_i in range(len(single_combination)):  # для каждой машины (и одного рейса из нее)
        current_load_time = start_load_time  # Определяем начальное время погрузки на складе
        reis_window_repeat = False  # Переменная для повтора рейса (попытка сдвинуть окно выезда авто к первой приемке в магазине)
        single_combination[auto_i].set_default()  # обнуление текущего времени авто, на случай перезапуска расчета
        already_checked = _algo_get_ignore_list(current_routes) # Уже проверенные точки
        # Удаляем из матрицы выигрышей те точки маршрута, которые уже распределены (нет смысла их постоянно перебирать)
        for idx in range(len(win_matrix)):
            win_matrix[idx] = [dot for dot in win_matrix[idx] if dot not in already_checked]
        # Найденная при переносе старта авто точка, с которой необходимо начать построение маршрута (нет смысла искать ее по матрице выигрышей)
        predefined_win_dot = None
        while True:  # Цикл создания маршрута (для проверки условий, подразумевающих полную перестройку маршрута)
            route, \
            auto_res, \
            dots_process_time_res, \
            load_time_fail, \
            first_early_dot\
                = _algo_main_get_single_route(
                        auto=single_combination[auto_i],
                        current_routes=current_routes,
                        delivery_dots=delivery_dots,
                        dots_process_time=dots_process_time,
                        current_load_time=current_load_time,
                        max_load_time=max_load_time,
                        params=params,
                        prev_combination=prev_combination,
                        win_matrix=win_matrix,
                        times_matrix=times_matrix,
                        predefined_win_dot=predefined_win_dot,
            )
            if not load_time_fail and route is None and auto_res is not None:  # Маршрут не расчитан
                # Проверка необходимости сдвинуть время старта автомобиля
                if not reis_window_repeat:  # если маршрут пуст - возможно необходимо сдвинуть время старта рейса
                    reis_window_repeat = True
                    min_current_time_corrected = None

                    if first_early_dot: # Если есть наиболее ранняя точка, которая прошла все проверки (кроме времени прибытия)
                        deliv_dot = delivery_dots[first_early_dot - 1]
                        min_current_time_corrected = deliv_dot.window_from \
                                                     - _get_trip_time(times_matrix[0][deliv_dot.matrix_idx]) \
                                                     - current_load_time \
                                                     - params['early_arrival']
                    if min_current_time_corrected is not None and \
                            min_current_time_corrected > single_combination[auto_i].current_time:
                        single_combination[auto_i].current_time = min_current_time_corrected  # Сдвигаем время рейса на окно магазина и пробуем снова
                        # Для пустого времени старта авто - зададим его принудительно при переносе времени
                        if single_combination[auto_i].current_reis == 1 and single_combination[auto_i].real_auto.start_time_free:
                            single_combination[auto_i].real_auto.start_time = single_combination[auto_i].current_time
                        predefined_win_dot = first_early_dot #Проставляем магазин, с которого надо начать построение маршрута
                        continue
            else:
                reis_window_repeat = False  # Сбрасываем значение повтора маршрута из-за переноса старта рейса
                predefined_win_dot = None # Сброс значения найденной точки при переносе старта рейса
                if load_time_fail: #Не попали в текущее время погрузки, увеличиваем его
                    current_load_time += step_load_time
                    single_combination[auto_i].set_default()  # Обнуляем текущее время авто, чтобы прошли весь цикл заново (в т.ч. сдвигания окон, если он был)
                    continue
            break
        # Добавление маршрута
        if route is not None:
            dots_process_time = dots_process_time_res
            if route.with_return:
                auto_res.current_time += _get_trip_time(times_matrix[route.dots[-1]][0])  # прибавляем время возврата на склад
            route.end_time = auto_res.current_time  # Записываем время окончания маршрута
            single_combination[auto_i] = auto_res
            prev_combination.append(single_combination[auto_i])
            current_routes.append(route)

    # Конец расчета для комбинации автомобилей
    if len(cached_combination) > 0:
        single_combination = cached_combination + single_combination

    # Добавление расчета в кэш
    cache[_combi_idx(single_combination)] = {
        'single_combination': single_combination,
        'current_routes': current_routes,
        'dots_process_time': dots_process_time,
        'base_combination': prev_combination
    }

    return current_routes, single_combination, dots_process_time


def _algo_main(win_matrix, times_matrix, delivery_dots, real_autos, dyn_auto, params):

    # Создание списка времени разгрузки в магазинах (потенциально-изменяемое поле при расчете)
    dots_process_time = []
    for deliv_dot in delivery_dots:
        dots_process_time.append(deliv_dot.process_time)

    """РАСЧЕТ"""
    result = {}
    reis_calc_default = {
        'single_combination': [],
        'current_routes': [],
        'dots_process_time': dots_process_time,
        'base_combination': []
    }
    best_reis_calc = copy.deepcopy(reis_calc_default)
    calc_cache = {} # Кэш рассчитанных маршрутов по полным комбинациям

    """Статические авто"""
    # Список автомобилей (по рейсам)
    auto_reis = _algo_get_auto_reis(real_autos, params['auto_min'])
    for auto_list in auto_reis: # Цикл по рейсам (в случае минимизации транспорта рейс всегда 1)
        while True: #Цикл по всем комбинациям в текущем рейсе
            base_combinations = _algo_auto_get_base_combinations(
                auto_list=auto_list,
                combination_list=best_reis_calc['base_combination'],
                auto_min=params['auto_min'],
            )
            if not base_combinations: # Если распределили все свободные машины - переходим к сл. рейсу
                break
            full_combinations = _algo_auto_get_full_combinations(
                auto_list=auto_list,
                base_combinations=base_combinations,
                high_accuracy=params['high_accuracy'],
                auto_min=params['auto_min'],
            )

            # Расчет базовых маршрутов в кэш, чтобы быстрее строились (достраивались) полные
            for base_comb in base_combinations:
                _algo_main_single_combination_calc(
                    cache=calc_cache,
                    single_combination=base_comb,
                    delivery_dots=delivery_dots,
                    dots_process_time=dots_process_time,
                    win_matrix=win_matrix,
                    times_matrix=times_matrix,
                    params=params,
                )
            # Итоговый расчет полных маршрутов
            prev_best_reis_calc = copy.deepcopy(best_reis_calc)
            for single_combination in full_combinations:
                current_routes_res, single_combination_res, dots_process_time_res = _algo_main_single_combination_calc(
                    cache=calc_cache,
                    single_combination=single_combination['full_combination'],
                    delivery_dots=delivery_dots,
                    dots_process_time=dots_process_time,
                    win_matrix=win_matrix,
                    times_matrix=times_matrix,
                    params=params,
                )
                is_best_calc, result = _algo_main_best_calc_compare(
                    best_calc=result,
                    current_routes=current_routes_res,
                    single_combination=single_combination_res,
                    delivery_dots=delivery_dots,
                    dots_process_time=dots_process_time_res,
                    win_matrix=win_matrix,
                )
                if is_best_calc:
                    best_reis_calc = {
                        'single_combination': single_combination_res,
                        'current_routes': current_routes_res,
                        'dots_process_time': dots_process_time_res,
                        'base_combination': single_combination['base_combination'],
                    }

            # Если в эту итерацию оптимальнее маршрута не нашлось - идём по той же ветке (к базовому прибавляем +1 точку)
            if _combi_idx(prev_best_reis_calc['base_combination']) == _combi_idx(best_reis_calc['base_combination']):
                if len(best_reis_calc['base_combination']) == len(best_reis_calc['single_combination']):
                    break # Уже добили маршрут максимальным кол-вом точек, необходимо переходить к сл. рейсу
                best_reis_calc['base_combination'] = best_reis_calc['single_combination'][:len(best_reis_calc['base_combination']) + 1]

    """Динамические авто"""
    for dyn_auto_count in range(1, dyn_auto['count_max'] + 1):
        # Генерация динамического авто
        dyn_real_auto = _RealAuto(
            capacity=dyn_auto['capacity'],
            reis_max=dyn_auto['reis_max'],
            start_time_free = True,
            driver_limit=dyn_auto['driver_limit'],
        )
        for reis_num in range(1, dyn_real_auto.reis_max + 1):
            dyn_auto_reis = _CurrentAuto(real_auto=dyn_real_auto, current_reis=reis_num)
            # Расчет по сгенерированному авто (рейсу из него)
            current_routes_res, single_combination_res, dots_process_time_res = _algo_main_single_combination_calc(
                cache=calc_cache,
                single_combination=best_reis_calc['single_combination'] + [dyn_auto_reis],
                delivery_dots=delivery_dots,
                dots_process_time=dots_process_time,
                win_matrix=win_matrix,
                times_matrix=times_matrix,
                params=params,
            )
            is_best_calc, result = _algo_main_best_calc_compare(
                best_calc=result,
                current_routes=current_routes_res,
                single_combination=single_combination_res,
                delivery_dots=delivery_dots,
                dots_process_time=dots_process_time_res,
                win_matrix=win_matrix,
            )
            if is_best_calc:
                best_reis_calc = {
                    'single_combination': single_combination_res,
                    'current_routes': current_routes_res,
                    'dots_process_time': dots_process_time_res,
                }
            else:
                break

    return result


# подготовка результата, преобразование в читаемый формат и сохранение в бд
def _algo_save_result(request_user, result, distance_matrix, times_matrix, store_dot, delivery_dots, real_autos, dyn_auto, params):

    route_set = RouteSet(
        username=request_user,
        store=store_dot.obj,
    )
    route_set.save()

    RouteStat(
        route_set=route_set,
        priority_bad=result['stat_priority_bad'],
        regular_bad=result['stat_regular_bad'],
        auto_count=result['stat_autos'],
        reis_count=result['stat_reis'],
        costs=result['stat_costs'],
        with_return=params['with_return'],
        high_accuracy=params['high_accuracy'],
        auto_min=params['auto_min'],
        early_arrival=params['early_arrival'],
        lately_arrival=params['lately_arrival'],
        dyn_auto_count_max=dyn_auto['count_max'],
        dyn_auto_capacity=dyn_auto['capacity'],
        dyn_auto_reis_max=dyn_auto['reis_max'],
        dyn_auto_driver_limit=dyn_auto['driver_limit'],
    ).save()

    route_dot_link = {}  # Связь объектов DeliveryDot и RouteDot
    for route in result['current_routes']:
        prev_dot = 0
        current_time = route.start_time + route.load_time #время прибытия на склад + время загрузки
        current_km = 0
        last_deliv_dot = delivery_dots[route.dots[-1:][0] - 1] #последняя точка доставки (для определения времени и км до склада в конце маршрута)
        # Поиск авто данного маршрута
        try: #Поиск статического авто
            real_auto = next(x for x in real_autos if x.num == route.auto_num)
        except StopIteration: # Авто в списке не нашлось => оно динамическое
            real_auto = None
        is_dyn_auto = False if real_auto else True
        result_route = Route(
            route_set=route_set,
            graph=route.auto_num,
            reis=route.reis_num,
            dyn_auto=is_dyn_auto,
            reis_start=route.start_time,
            load_time=route.load_time,
            store_return_distance=0 if not last_deliv_dot else distance_matrix[last_deliv_dot.matrix_idx][0],
            store_return_time=0 if not last_deliv_dot else _get_trip_time(times_matrix[last_deliv_dot.matrix_idx][0]),
        )
        result_route.save()

        for idx, dot in enumerate(route.dots):
            deliv_dot = delivery_dots[dot - 1]
            path_to_dot = distance_matrix[prev_dot][dot]
            current_km += path_to_dot
            current_time += _get_trip_time(times_matrix[prev_dot][dot])
            if current_time < deliv_dot.window_from: # если у нас были сдвинуты окна доставки и водитель подождал - запишем время ожидания
                wait_time = deliv_dot.window_from - current_time
                current_time = deliv_dot.window_from
            else:
                wait_time = 0
            time_in = current_time
            current_time += result['dots_process_time'][deliv_dot.idx]
            time_out = current_time
            prev_dot = dot
            route_dot = RouteDot(
                route=result_route,
                num=idx + 2,
                time_in=time_in,
                time_out=time_out,
                wait_time=wait_time,
                distance=path_to_dot,
            )
            route_dot.save()
            route_dot_link[deliv_dot] = route_dot

    #Сохранение исходных данных от пользователя
    bulk_save = []
    for real_auto in real_autos:
        #Поиск времени старта авто (для незаданного времени старта)
        if real_auto.start_time_free:
            try:
                real_auto.start_time = next(x.start_time for x in result['current_routes'] if x.auto_num == real_auto.num
                                            and x.reis_num == 1)
            except StopIteration: # Если нет маршрута
                pass
        bulk_save.append(RouteInitAuto(
            route_set=route_set,
            num=real_auto.num,
            name=real_auto.name,
            capacity=real_auto.capacity,
            reis_max=real_auto.reis_max,
            reis_start=real_auto.start_time,
            reis_start_free=real_auto.start_time_free,
            driver_limit=real_auto.driver_limit,
        ))
    RouteInitAuto.objects.bulk_create(bulk_save)
    bulk_save = []
    for deliv_dot in delivery_dots:
        route_dot = route_dot_link.get(deliv_dot)
        bulk_save.append(RouteInitDot(
            route_set=route_set,
            route_dot=route_dot,
            client=deliv_dot.obj,
            client_name=deliv_dot.client_name,
            client_address=deliv_dot.client_address,
            latitude=deliv_dot.latitude,
            longtitude=deliv_dot.longtitude,
            quantity=deliv_dot.quantity,
            window_in=deliv_dot.window_from,
            window_out=deliv_dot.window_to,
            process_time=deliv_dot.process_time,
            priority=deliv_dot.priority,
        ))
    RouteInitDot.objects.bulk_create(bulk_save)
    return route_set.id


#Public методы форматирования\сохранения инф-ции
def format_to_time(time_seconds): #Преобразование числа секунд с полночи в час:минуты
    time_seconds = time_seconds % 86400 # Время может быть текущим, предыдущим или последующим днём
    return time.strftime('%H:%M', time.gmtime(time_seconds))


def format_to_duration(time_seconds): #Преобразование числа секунд с полночи в Hч. Mм.
    time_minutes = time_seconds // 60
    hours = time_minutes // 60
    minutes = time_minutes % 60
    return f"{hours}ч. {minutes}м."


def format_to_km(path_km):
    return round(path_km / 1000, 2)


def output_result_db_to_csv(route_set): #выгрузка во временный файл в csv из бд списка маршрутов
    """график(номер машины);рейс;магазин;широта;долгота;кол-во лотков;время убытия с хз(старт машины);время прибытия;время убытия;код магазина"""
    def add_row(graph, reis, cli_name, cli_address, latitude, longtitude, quantity, reis_start, reis_start_loaded, time_in, time_out,
                window_in, window_out, path_to_dot, cli_code):
        row = {
            'График': graph,
            'Рейс': reis,
            'Магазин': cli_name,
            'Адрес': cli_address,
            'Широта': latitude,
            'Долгота': longtitude,
            'Кол-во лотков': round(quantity),
            'Прибытие на погрузку': format_to_time(reis_start),
            'Убытие с погрузки': format_to_time(reis_start_loaded),
            'Время прибытия в маг': format_to_time(time_in),
            'Время убытия с маг': format_to_time(time_out),
            'Окно приемки с': format_to_time(window_in),
            'Окно приемки по': format_to_time(window_out),
            'Расстояние от пред. точки': f"{format_to_km(path_to_dot)}",
            'Код магазина': cli_code,
        }
        return row


    rows = []
    route_list = Route.objects.filter(route_set=route_set)
    for route in sorted(route_list, key = lambda i: (i.graph, i.reis)):
        delivery_dots = RouteDot.objects.filter(route=route)
        for dot in delivery_dots:
            dot_init = dot.get_init_dot()
            dot_client = dot_init.client
            client_address = dot_init.client_address
            if dot_client:
                client_name = f"{dot_client.ns_code} {dot_init.client_name}"
                if not client_address:
                    client_address = dot_client.address
                ns_code = dot_client.ns_code
            else:
                client_name = dot_init.client_name
                ns_code = ''
            #client_address = dot_client.address if dot_client else ''
            dot_latitude = dot_init.latitude
            dot_longtitude = dot_init.longtitude
            if not dot_latitude or not dot_longtitude:
                dot_latitude = dot_client.latitude
                dot_longtitude = dot_client.longtitude
            rows.append(add_row(
                graph=route.graph,
                reis=route.reis,
                cli_name=client_name,
                cli_address=client_address,
                latitude=dot_latitude,
                longtitude=dot_longtitude,
                quantity=dot_init.quantity,
                reis_start=route.reis_start,
                reis_start_loaded=route.reis_start + route.load_time,
                time_in=dot.time_in,
                time_out=dot.time_out,
                window_in=dot_init.window_in,
                window_out=dot_init.window_out,
                path_to_dot=dot.distance,
                cli_code=ns_code,
            ))

    route_stat = RouteStat.objects.get(route_set=route_set)

    with NamedTemporaryFile(mode='w', newline='', delete=False, encoding='cp1251') as csvfile:
        writer = csv.DictWriter(csvfile,  delimiter=';', fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

        writer = csv.writer(csvfile, delimiter=';')
        writer.writerow([''])
        writer.writerow(['Общая статистика'])
        writer.writerow(['Нераспределенных приоритетных точек:', route_stat.priority_bad])
        writer.writerow(['Нераспределенных обычных точек:', route_stat.regular_bad])
        writer.writerow(['Автомобилей использовано:', route_stat.auto_count])
        writer.writerow(['Рейсов использовано:', route_stat.reis_count])
        writer.writerow(['Временные затраты всего:', format_to_duration(route_stat.costs)])

        return csvfile.name


#Public класс, который необходимо использовать для расчета
class RouteCalc:
    def __init__(self, request, store_object, auto_list, delivery_dots_list, dyn_auto, params):
        self.request_user = request.user
        self._store_dot = _fill_store_dots(store_object)  # точка склад, который задает пользователь
        self._real_autos = _fill_real_autos(auto_list) #Авто, как их зададут пользователи
        self._delivery_dots = _fill_delivery_dots(delivery_dots_list) #точки доставки, которые задают пользователи
        # Динамические авто (параметры)
        # count_max - Максимальное кол-во дин.автомобилей
        # capacity - Ёмкость
        # reis_max - Максимальное кол-во рейсов для авто
        # driver_limit - Смена водителя
        self._dyn_auto = dyn_auto
        #Параметры расчета:
        # with_return  - Расчет с возвратом на склад
        # high_accuracy - Режим высокой точности (расчет ведется по наиболее полной комбинации)
        # auto_min - Режим минимизации статического транспорта
        # early_arrival  - На сколько можно приехать раньше окна доставки магазина (кроме приоритетных магазинов)
        # lately_arrival  - На сколько можно приехать позже окна доставки магазина (кроме приоритетных магазинов)
        self._params = params

    def calculate_and_save(self): #расчет
        #Проверки на технические ограничения
        # if len(self._real_autos) > 15 and not settings.DEBUG:
        #     raise ValueError("Расчет более 15 авто в маршруте недоступен")
        if not len(self._real_autos) and not self._dyn_auto['count_max']:
            raise ValueError("Укажите хотя бы 1 авто (обычный или динамический)")
        # if len(self._real_autos) > 0 and len(self._delivery_dots) > 500 and not settings.DEBUG:
        #     raise ValueError("Расчет более 500 ТТ в маршруте со статическими авто недоступен")
        if len(self._delivery_dots) > 1000:
            raise ValueError("Расчет более 1000 ТТ в маршруте недоступен")
        if settings.DEBUG:
            pr = cProfile.Profile()
            pr.enable()
        # Получение матрицы расстояний и времени
        self._win_matrix, self._distance_matrix, self._times_matrix, self._store_dot, self._delivery_dots = _get_distance_matrix(self._store_dot, self._delivery_dots)
        # Основной расчет
        self._result = _algo_main(
            self._win_matrix,
            self._times_matrix,
            self._delivery_dots,
            self._real_autos,
            self._dyn_auto,
            self._params,
        )
        # Сохранение результата в БД
        id = _algo_save_result(
            self.request_user,
            self._result,
            self._distance_matrix,
            self._times_matrix,
            self._store_dot,
            self._delivery_dots,
            self._real_autos,
            self._dyn_auto,
            self._params,
        )
        if settings.DEBUG:
            pr.disable()
            pr.print_stats(sort="time")
        return id
