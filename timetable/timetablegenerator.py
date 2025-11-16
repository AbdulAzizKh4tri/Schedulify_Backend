from django.core.exceptions import ValidationError
import copy
import random
import pandas as pd
import time
from django.db import IntegrityError, transaction

from .models import TIME_SLOTS

# Set up logginglogging.basicConfig(level=logging.INFO)

SINGLE_SLOT = "Lecture"
DOUBLE_SLOT = "Lab"
WORKDAY_COUNT = 6

def get_teacher_workload(teacher, timetable_entries):
    """Calculate current workload of a teacher based on assigned slots."""
    return timetable_entries.filter(teacher=teacher).count() or 0

def get_modifiable_entity_array(model_class, id_list=None):
    # Get all non-relational field names from the model
    fields = [field.name for field in model_class._meta.get_fields() if not field.is_relation]
    
    # Query all entity objects and get all fields
    if id_list:
        queryset = model_class.objects.filter(id__in=id_list).values(*fields)
    else:
        queryset = model_class.objects.all().values(*fields)

    if(queryset is None):
        raise ValidationError(f"No objects for {model_class}")
    
    # Create a deep copy to ensure no DB connection
    data_list = [copy.deepcopy(item) for item in list(queryset)]
    
    df = pd.DataFrame(data_list)
    df.set_index('id', inplace=True)
    return df

def set_availability(df, entity_id, slot, available):
    s = list(df.at[entity_id, 'availability'])
    s[slot] = '1' if available else '0'
    df.at[entity_id, 'availability'] = ''.join(s)

def is_available(df, entity_id, slot):
    """Check if a given entity is available at a slot."""
    return df.at[entity_id, 'availability'][slot] == '1'

def same_subject_in_day_exists(division_id, subject_id, slot, session_type, current_allocations):
    day = slot % WORKDAY_COUNT
    for _, s_id, d_id, s, _, _ in current_allocations:
        if d_id == division_id and s_id == subject_id and s % WORKDAY_COUNT == day:
            return True
    return False

iterations = 0
def try_allocate(assignment_index, assignments, teachers, classrooms, divisions, current_allocations,start_time, timeout):
        """Recursive backtracking allocation."""

        global iterations
        if iterations % 1000 == 0:
            print(f"Iterations: {iterations}, Current allocations: {len(current_allocations)}/{len(assignments)}")
        iterations += 1

        if timeout and (time.time() - start_time) > timeout:
            raise TimeoutError("Timetable generation timed out")

        if assignment_index == len(assignments):
            return []  # success, no more to assign

        teacher_id, subject_id, division_id, session_type = assignments[assignment_index]

        candidate_slots = []
        for slot in range(TIME_SLOTS):
            if not is_available(teachers, teacher_id, slot):
                continue
            if not is_available(divisions, division_id, slot):
                continue
            if session_type == SINGLE_SLOT:
                for room_id in classrooms.index:
                    if not is_available(classrooms, room_id, slot):
                        continue

                    violates_soft = same_subject_in_day_exists(division_id, subject_id, slot, session_type, current_allocations)
                    candidate_slots.append((violates_soft, slot, room_id))

            elif session_type == DOUBLE_SLOT:
                if not (slot // WORKDAY_COUNT) % 2 == 0 or slot+WORKDAY_COUNT >= TIME_SLOTS:
                    continue
                if not is_available(teachers,teacher_id,slot+WORKDAY_COUNT):
                    continue
                if not is_available(divisions,division_id,slot+WORKDAY_COUNT):
                    continue

                for room_id in classrooms.index:
                    if not (is_available(classrooms, room_id, slot) and is_available(classrooms,room_id,slot+WORKDAY_COUNT)):
                        continue
                    violates_soft = same_subject_in_day_exists(division_id, subject_id, slot, session_type, current_allocations)
                    candidate_slots.append((violates_soft, slot, room_id))
        
        candidate_slots.sort(key=lambda x: x[0])

        for _, slot, room_id in candidate_slots:
            set_availability(teachers, teacher_id, slot, False)
            set_availability(divisions, division_id, slot, False)
            set_availability(classrooms, room_id, slot, False)
            if session_type == DOUBLE_SLOT:
                set_availability(teachers, teacher_id, slot+WORKDAY_COUNT, False)
                set_availability(divisions, division_id, slot+WORKDAY_COUNT, False)
                set_availability(classrooms, room_id, slot+WORKDAY_COUNT, False)

            # Continue with next assignment
            result = try_allocate(assignment_index + 1, assignments, teachers, classrooms, divisions, 
                                    current_allocations + [(teacher_id, subject_id, division_id, slot, room_id, session_type)], start_time, timeout)
            if result is not None:  # success
                return result + [(teacher_id, subject_id, division_id, slot, room_id, session_type)]

            # Rollback
            set_availability(teachers, teacher_id, slot, True)
            set_availability(divisions, division_id, slot, True)
            set_availability(classrooms, room_id, slot, True)
            if session_type == DOUBLE_SLOT:
                set_availability(teachers, teacher_id, slot+WORKDAY_COUNT, True)
                set_availability(divisions, division_id, slot+WORKDAY_COUNT, True)
                set_availability(classrooms, room_id, slot+WORKDAY_COUNT, True)

        return None  # no valid allocation found



def generate_timetable(timeout=5000, teacher_ids=None, classroom_ids=None, division_ids=None):
    """Generate a timetable maximizing teacher preferences and balancing workload."""
    from .models import Division, Subject, Teacher, ClassRoom, Preference, Timetable,TimetableEntry, TIME_SLOTS, MAXIMUM_WORK_LOAD
    from .utils import get_teacher_subject_division_mapping
    
    start_time = time.time()

    def check_timeout():
        if timeout and (time.time() - start_time) > timeout:
            raise TimeoutError("Timetable generation timed out.")


    teachers = get_modifiable_entity_array(Teacher,teacher_ids)
    classrooms = get_modifiable_entity_array(ClassRoom, classroom_ids)
    divisions = get_modifiable_entity_array(Division, division_ids)
    
    LP_output = get_teacher_subject_division_mapping(require_preference=True)

    assignments = []
    for assignment in LP_output['assignments']:
        for _ in range(Subject.objects.get(id=assignment[1]).lectures_per_week):
            assignments.append(list(assignment) + [SINGLE_SLOT])
        for _ in range(Subject.objects.get(id=assignment[1]).labs_per_week):
            assignments.append(list(assignment)+[DOUBLE_SLOT])

    
    random.shuffle(assignments)

    allocations = try_allocate(0, assignments, teachers, classrooms, divisions, [],start_time, timeout)

    if allocations is None:
        print("No full timetable possible")
        return None


    try:
        with transaction.atomic():

            new_timetable = Timetable.objects.create()
            timetable_entries = [
                TimetableEntry(
                    teacher_id=t_id,
                    subject_id=s_id,
                    division_id=d_id,
                    classroom_id=r_id,
                    time_slot=slot,
                    session_type=session_type,
                    timetable_id=new_timetable.id
                )
                for t_id, s_id, d_id, slot, r_id, session_type in allocations
            ]
            TimetableEntry.objects.bulk_create(timetable_entries)

    except IntegrityError as e:
        raise
        
    return LP_output