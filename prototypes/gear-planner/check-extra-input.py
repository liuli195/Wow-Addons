import copy
import server
server.validate(server.BASE)
for value in ['9'*100000, '9'*2999+'!', '1:1/', '/1:1', '1::1', '1:1/2', '１:1', 123, ['1:1']]:
    model=copy.deepcopy(server.BASE);model['character']['omnium_talents']=value
    try:server.validate(model)
    except ValueError:pass
    else:raise AssertionError(value)
for value in ['1:1','136814:1/136821:1','']:
    model=copy.deepcopy(server.BASE);model['character']['omnium_talents']=value;server.validate(model)
print('PASS: bounded linear extra talent validation; valid lists and malformed/adversarial input')
