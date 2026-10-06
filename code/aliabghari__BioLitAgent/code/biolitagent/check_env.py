for l in open('.env'):
    if l.startswith('NCBI_'):
        k, v = l.strip().split('=', 1)
        print(k, '-> length', len(v), '| looks like placeholder:', 'example.com' in v.lower() or 'free key' in v.lower() or v.strip() == '')
